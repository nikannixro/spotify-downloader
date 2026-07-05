"""spotDL backend — download engine using the spotdl library."""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import shutil
from pathlib import Path
import tempfile
from typing import Any

from mutagen.flac import FLAC

from config import cfg
from models import DownloadResult, TrackMetadata

logger = logging.getLogger(__name__)

_spotdl_initialized = False


def _ensure_spotdl_init() -> None:
    """Initialize spotDL SpotifyClient exactly once."""
    global _spotdl_initialized
    if _spotdl_initialized:
        return
    from spotdl.utils.spotify import SpotifyClient

    SpotifyClient.init(
        client_id=cfg.SPOTIFY_CLIENT_ID,
        client_secret=cfg.SPOTIFY_CLIENT_SECRET,
        no_cache=True,
        headless=True,
        use_official_api=True,
    )
    logging.getLogger("spotdl").setLevel(logging.DEBUG)
    _spotdl_initialized = True
    logger.info("spotDL SpotifyClient initialized")


def _song_to_metadata(song) -> TrackMetadata:
    """Convert a spotDL Song object to the bot's TrackMetadata."""
    artists_str = ", ".join(song.artists) if song.artists else song.artist or "Unknown"
    release_date = song.date or ""
    release_year = str(song.year) if song.year else ""

    return TrackMetadata(
        track_id=song.song_id or "",
        name=song.name or "Unknown",
        artists=artists_str,
        album=song.album_name or "",
        release_date=release_date,
        release_year=release_year,
        cover_url=song.cover_url,
        track_number=song.track_number or 0,
        disc_number=song.disc_number or 0,
        genres=song.genres or [],
        duration_ms=song.duration * 1000 if song.duration else 0,
        isrc=song.isrc,
        composer=None,
        writer=None,
        publisher=song.publisher or None,
        label=song.publisher or None,
    )


def _post_process_flac(file_path: str, meta: TrackMetadata) -> None:
    """Post-process FLAC: clean tags, re-encode to 24-bit 48kHz, then embed metadata."""
    try:
        audio = FLAC(file_path)
        for tag in ["encoder", "comment", "encodedby", "woas", "isrc", "description"]:
            if tag in audio:
                del audio[tag]
        audio.save()

        re_encoded = _ffmpeg_reencode_flac(file_path)
        if re_encoded and os.path.exists(re_encoded):
            os.replace(re_encoded, file_path)
            logger.info("Re-encoded FLAC: %s", os.path.basename(file_path))

        audio = FLAC(file_path)

        audio["artist"] = [meta.artists]
        audio["title"] = [meta.name]
        audio["album"] = [meta.album]
        audio["tracknumber"] = [str(meta.track_number)]
        audio["date"] = [meta.release_date]

        if meta.genres:
            audio["genre"] = [meta.genres[0]]
        if meta.publisher:
            audio["publisher"] = [meta.publisher]
        if meta.composer:
            audio["composer"] = [meta.composer]
        if meta.language:
            audio["language"] = [meta.language]

        if meta.cover_url:
            _embed_cover_art(audio, meta.cover_url)

        audio.save()
        logger.info("Metadata embedded for %s", os.path.basename(file_path))
    except Exception as exc:
        logger.warning("Post-processing failed for %s: %s", file_path, exc)


def _embed_cover_art(audio: FLAC, cover_url: str) -> None:
    """Download and embed cover art into FLAC file."""
    import requests as req
    from mutagen.flac import Picture

    try:
        resp = req.get(cover_url, timeout=15)
        resp.raise_for_status()
        cover_data = resp.content
        picture = Picture()
        picture.type = 3
        picture.desc = "Cover"
        picture.mime = "image/jpeg"
        picture.data = cover_data
        audio.add_picture(picture)
    except Exception as exc:
        logger.warning("Failed to embed cover art: %s", exc)


def _ffmpeg_reencode_flac(file_path: str) -> str | None:
    """Re-encode FLAC with sample_fmt s24, compression_level 0, 48kHz."""
    import subprocess

    file_path = os.path.abspath(file_path)
    output_path = file_path + ".reenc.flac"
    cmd = [
        "ffmpeg", "-y",
        "-i", file_path,
        "-map_metadata", "0",
        "-codec:a", "flac",
        "-sample_fmt", "s32",
        "-compression_level", "0",
        "-ar", "48000",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
        stderr = result.stderr.decode(errors="replace")
        logger.warning("FFmpeg re-encode failed (code %d): %s", result.returncode, stderr[-500:])
        if os.path.exists(output_path):
            os.remove(output_path)
        return None
    except Exception as exc:
        logger.warning("FFmpeg re-encode error: %s", exc)
        if os.path.exists(output_path):
            os.remove(output_path)
        return None


def _build_filename(meta: TrackMetadata) -> str:
    """Build safe filename: ARTIST - TITLE.flac"""
    from utils.helpers import sanitize_filename

    artist = sanitize_filename(meta.artists.split(",")[0].strip())
    title = sanitize_filename(meta.name)
    return f"{artist} - {title}.flac"





def _set_event_loop_for_worker() -> None:
    """Ensure the current thread has an event loop (needed for spotDL in executor threads)."""
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _run_spotdl_fetch_song(url: str):
    """Fetch Song from URL with event loop setup for worker thread."""
    _set_event_loop_for_worker()
    from spotdl.types.song import Song

    try:
        return Song.from_url(url)
    except Exception as exc:
        logger.error("Failed to fetch song from %s: %s", url, exc)
        return None


async def _musicbrainz_lookup(isrc: str | None) -> dict[str, str | None]:
    """Look up composer, publisher, language, genres via MusicBrainz ISRC."""
    result = {"composer": None, "writer": None, "publisher": None, "label": None, "language": None, "genres": []}
    if not isrc:
        return result

    try:
        import musicbrainzngs

        musicbrainzngs.set_useragent("SpotifyDownloaderBot", "2.0", "")

        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(
            None, functools.partial(musicbrainzngs.get_recordings_by_isrc, isrc, includes=["artists", "releases"])
        )

        recordings = data.get("isrc", {}).get("recording-list", [])
        if not recordings:
            logger.debug("MusicBrainz: no recordings for ISRC %s", isrc)
            return result

        recording = recordings[0]

        for credit in recording.get("artist-credit", recording.get("artist-credit-list", [])):
            artist = credit.get("artist", {})
            artist_name = artist.get("name", "")
            if artist_name and not result["composer"]:
                result["composer"] = artist_name

        releases = recording.get("release-list", [])
        if releases:
            release = releases[0]

            label_info_list = release.get("label-info-list")
            if label_info_list:
                label_info = label_info_list[0]
                label = label_info.get("label", {})
                label_name = label.get("name", "")
                if label_name:
                    result["label"] = label_name
                    result["publisher"] = label_name

            text_rep = release.get("text-representation", {})
            lang = text_rep.get("language")
            if lang:
                result["language"] = lang

        recording_id = recording.get("id")
        if recording_id:
            try:
                rec_data = await loop.run_in_executor(
                    None, functools.partial(musicbrainzngs.get_recording_by_id, recording_id, includes=["tags"])
                )
                tags = rec_data.get("recording", {}).get("tag-list", [])
                genres = [t["name"] for t in tags if t.get("count", 0) >= 1]
                if genres:
                    result["genres"] = genres[:5]
            except Exception:
                pass

        logger.info("MusicBrainz ISRC %s -> %s", isrc, result)
    except Exception as exc:
        logger.warning("MusicBrainz lookup failed for ISRC %s: %s", isrc, exc)

    return result


async def _deezer_fallback(isrc: str | None, artist: str, title: str) -> dict[str, Any]:
    """Search Deezer for genre and publisher as fallback."""
    result: dict[str, Any] = {"genres": [], "publisher": None}
    loop = asyncio.get_running_loop()

    try:
        track_data = None
        if isrc:
            track_data = await loop.run_in_executor(
                None, _deezer_fetch_by_isrc, isrc
            )

        if not track_data:
            track_data = await loop.run_in_executor(
                None, _deezer_search_track, artist, title
            )

        if not track_data:
            return result

        album_id = track_data.get("album", {}).get("id")
        if album_id:
            album_data = await loop.run_in_executor(
                None, _deezer_fetch_album, album_id
            )
            if album_data:
                genres = album_data.get("genres", {}).get("data", [])
                if genres:
                    result["genres"] = [g.get("name") for g in genres if g.get("name")]
                label = album_data.get("label")
                if label:
                    result["publisher"] = label

        logger.info("Deezer fallback: genres=%s, publisher=%s", result["genres"], result["publisher"])
    except Exception as exc:
        logger.warning("Deezer fallback failed: %s", exc)

    return result


def _deezer_fetch_by_isrc(isrc: str) -> dict | None:
    """Fetch track from Deezer by ISRC (blocking)."""
    import requests
    try:
        r = requests.get(f"https://api.deezer.com/track/isrc:{isrc}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("id"):
                return data
    except Exception:
        pass
    return None


def _deezer_search_track(artist: str, title: str) -> dict | None:
    """Search Deezer for a track by artist and title (blocking)."""
    import requests
    try:
        query = f'artist:"{artist}" track:"{title}"'
        r = requests.get("https://api.deezer.com/search", params={"q": query, "limit": 1}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            results = data.get("data", [])
            if results:
                return results[0]
    except Exception:
        pass
    return None


def _deezer_fetch_album(album_id: int) -> dict | None:
    """Fetch album details from Deezer (blocking)."""
    import requests
    try:
        r = requests.get(f"https://api.deezer.com/album/{album_id}", timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


async def _enrich_metadata(meta: TrackMetadata) -> None:
    """Enrich metadata with MusicBrainz and Deezer data."""
    mb_data = await _musicbrainz_lookup(meta.isrc)
    if mb_data.get("composer") and not meta.composer:
        meta.composer = mb_data["composer"]
    if mb_data.get("language"):
        meta.language = mb_data["language"]

    dz_data = None
    if not meta.genres or not meta.publisher:
        if (not meta.genres and not mb_data.get("genres")) or (not meta.publisher and not mb_data.get("publisher")):
            dz_data = await _deezer_fallback(meta.isrc, meta.artists, meta.name)

    if not meta.genres:
        if mb_data.get("genres"):
            meta.genres = mb_data["genres"]
        elif dz_data and dz_data.get("genres"):
            meta.genres = dz_data["genres"]

    if not meta.publisher:
        if mb_data.get("publisher"):
            meta.publisher = mb_data["publisher"]
        elif dz_data and dz_data.get("publisher"):
            meta.publisher = dz_data["publisher"]

    if mb_data.get("label") and not meta.label:
        meta.label = mb_data["label"]

    logger.debug("Enriched metadata: publisher=%s, genres=%s, language=%s, composer=%s",
        meta.publisher, meta.genres, meta.language, meta.composer)


class SpotDLBackend:
    """Download engine using the spotdl library."""

    def __init__(self) -> None:
        _ensure_spotdl_init()

    async def download_track(self, track_url: str, user_id: int = 0) -> DownloadResult:
        """Download a single Spotify track."""
        from plugins.download_manager import register_temp_dir, unregister_temp_dir
        from plugins.ytdl import download_track as ytdl_download

        tmp_dir = tempfile.mkdtemp(prefix="spotdl_")
        if user_id:
            register_temp_dir(user_id, tmp_dir)

        try:
            loop = asyncio.get_running_loop()

            song = await loop.run_in_executor(
                None, _run_spotdl_fetch_song, track_url
            )
            if song is None:
                return DownloadResult(success=False, error="Failed to fetch track metadata")

            artists = song.artists if song.artists else [song.artist or "Unknown"]
            query = f"{artists[0]} - {song.name}"
            cookie_file = str(Path(cfg.COOKIE_FILE).resolve()) if cfg.COOKIE_FILE else None

            file_path = await loop.run_in_executor(
                None, ytdl_download, query, tmp_dir, cookie_file
            )

            if file_path is None or not os.path.isfile(file_path):
                return DownloadResult(success=False, error="Download failed")

            meta = _song_to_metadata(song)
            logger.debug("SpotDL metadata: publisher=%s, genres=%s, isrc=%s", meta.publisher, meta.genres, meta.isrc)

            await _enrich_metadata(meta)

            safe_name = _build_filename(meta)
            final_path = os.path.join(tmp_dir, safe_name)
            if os.path.abspath(file_path) != os.path.abspath(final_path):
                shutil.move(file_path, final_path)

            _post_process_flac(final_path, meta)

            logger.info("Download complete: %s", safe_name)
            return DownloadResult(
                success=True,
                file_path=final_path,
                filename=safe_name,
                metadata=meta,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Download failed for %s: %s", track_url, exc)
            return DownloadResult(success=False, error=f"Download error: {exc}")
        finally:
            if user_id:
                unregister_temp_dir(user_id, tmp_dir)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def download_song(self, song, user_id: int = 0) -> DownloadResult:
        """Download a pre-fetched spotDL Song object."""
        from plugins.download_manager import register_temp_dir, unregister_temp_dir
        from plugins.ytdl import download_track as ytdl_download

        tmp_dir = tempfile.mkdtemp(prefix="spotdl_")
        if user_id:
            register_temp_dir(user_id, tmp_dir)

        try:
            loop = asyncio.get_running_loop()

            artists = song.artists if song.artists else [song.artist or "Unknown"]
            query = f"{artists[0]} - {song.name}"
            cookie_file = str(Path(cfg.COOKIE_FILE).resolve()) if cfg.COOKIE_FILE else None

            file_path = await loop.run_in_executor(
                None, ytdl_download, query, tmp_dir, cookie_file
            )

            if file_path is None or not os.path.isfile(file_path):
                return DownloadResult(success=False, error="Download failed")

            meta = _song_to_metadata(song)
            logger.debug("SpotDL metadata: publisher=%s, genres=%s, isrc=%s", meta.publisher, meta.genres, meta.isrc)

            await _enrich_metadata(meta)

            safe_name = _build_filename(meta)
            final_path = os.path.join(tmp_dir, safe_name)
            if os.path.abspath(file_path) != os.path.abspath(final_path):
                shutil.move(file_path, final_path)

            _post_process_flac(final_path, meta)

            logger.info("Download complete: %s", safe_name)
            return DownloadResult(
                success=True,
                file_path=final_path,
                filename=safe_name,
                metadata=meta,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Download failed: %s", exc)
            return DownloadResult(success=False, error=f"Download error: {exc}")
        finally:
            if user_id:
                unregister_temp_dir(user_id, tmp_dir)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    async def get_album_songs(self, album_url: str) -> tuple[dict[str, Any] | None, list]:
        """Fetch album metadata and songs."""
        from spotdl.types.album import Album

        loop = asyncio.get_running_loop()
        try:
            album = await loop.run_in_executor(
                None, functools.partial(Album.from_url, album_url, fetch_songs=True)
            )
            info = {
                "name": album.name,
                "artists": [{"name": album.artist.get("name", "Unknown")}] if isinstance(album.artist, dict) else [{"name": str(album.artist)}],
                "images": [],
                "release_date": "",
                "total_tracks": len(album.songs),
            }
            if album.songs and album.songs[0].cover_url:
                info["images"] = [{"url": album.songs[0].cover_url}]
            if album.songs and album.songs[0].date:
                info["release_date"] = album.songs[0].date
            return info, album.songs
        except Exception as exc:
            logger.exception("Failed to fetch album: %s", exc)
            return None, []

    async def get_playlist_songs(self, playlist_url: str) -> tuple[dict[str, Any] | None, list]:
        """Fetch playlist metadata and songs."""
        from spotdl.types.playlist import Playlist

        loop = asyncio.get_running_loop()
        try:
            playlist = await loop.run_in_executor(
                None, functools.partial(Playlist.from_url, playlist_url, fetch_songs=True)
            )
            info = {
                "name": playlist.name,
                "tracks": {"total": len(playlist.songs)},
                "images": [],
                "owner": {"display_name": playlist.author_name},
            }
            if playlist.cover_url:
                info["images"] = [{"url": playlist.cover_url}]
            return info, playlist.songs
        except Exception as exc:
            logger.exception("Failed to fetch playlist: %s", exc)
            return None, []
