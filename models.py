"""Data models used across the bot."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class SearchType(enum.Enum):
    """Spotify search category."""

    TRACK = "track"
    ARTIST = "artist"
    ALBUM = "album"
    PLAYLIST = "playlist"


class AdminState(enum.IntEnum):
    """Admin conversation flow states."""

    ADMIN_CHOOSE = 0
    WAIT_START_MSG = 1
    WAIT_BROADCAST = 2
    WAIT_BROADCAST_CONFIRM = 3
    WAIT_CHAN_ID = 4
    WAIT_RATE_LIMIT = 5
    WAIT_RATE_WINDOW = 6
    WAIT_JOIN_MSG = 7
    WAIT_LOG_CHANNEL = 8


@dataclass
class TrackMetadata:
    """Metadata returned by the Spotify API for a single track."""

    track_id: str
    name: str
    artists: str
    album: str
    release_date: str
    release_year: str = ""
    cover_url: str | None = None
    track_number: int = 0
    disc_number: int = 0
    genres: list[str] = field(default_factory=list)
    duration_ms: int = 0
    isrc: str | None = None
    composer: str | None = None
    writer: str | None = None
    publisher: str | None = None
    label: str | None = None
    language: str | None = None

    def __post_init__(self) -> None:
        if self.release_date and len(self.release_date) >= 4:
            self.release_year = self.release_date[:4]


@dataclass
class DownloadResult:
    """Result returned after a download attempt."""

    success: bool
    file_path: str | None = None
    filename: str | None = None
    error: str | None = None
    metadata: TrackMetadata | None = None
    from_cache: bool = False


@dataclass
class ChannelRecord:
    """A Telegram channel used for mandatory-join enforcement."""

    channel_id: str
    channel_title: str
    invite_link: str


@dataclass
class CacheEntry:
    """A single cached audio file tracked in the database."""

    track_id: str
    file_path: str
    filename: str
    created_at: str
    size_bytes: int = 0
