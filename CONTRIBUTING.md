# Contributing to Spotify Downloader Bot

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/nikannixro/Spotify-Downloader.git
   cd Spotify-Downloader
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   venv\Scripts\activate     # Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Copy environment variables:**
   ```bash
   cp example.env config.env
   # Edit config.env with your credentials
   ```

5. **Run the bot:**
   ```bash
   python main.py
   ```

## Code Style

- Follow PEP 8
- Use type hints
- Keep functions focused and small
- Write docstrings for public functions
- Use `async/await` for all database and I/O operations

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Commit with a clear message
5. Push to your fork
6. Open a Pull Request

## Reporting Issues

- Use GitHub Issues
- Include steps to reproduce
- Include error messages and logs
- Specify Python version and OS
