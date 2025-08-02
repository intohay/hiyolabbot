# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HiyoLab Bot is a Discord and Twitter notification bot that monitors Hiyori Hamagishi's fan club page for updates. It uses web scraping to detect changes and posts notifications to both platforms.

## Development Commands

```bash
# Install dependencies (using uv package manager)
uv pip install --requirements pyproject.toml

# Install Playwright browsers (required for member page monitoring)
playwright install chromium

# Run the bot
python src/hiyolabbot/main.py

# Run watcher standalone
python src/hiyolabbot/watcher.py

# Run tests
PYTHONPATH=src python -m unittest discover tests

# Environment setup
cp .env.example .env
# Then edit .env with required tokens
```

## Architecture

The codebase follows a modular architecture:

1. **main.py** - Discord bot entry point that:
   - Initializes Discord and Twitter clients
   - Runs a 60-second monitoring loop
   - Handles notifications and error reporting
   - Uses timestamp-based Twitter URLs to avoid duplicate detection
   - Integrates both public and member page monitoring

2. **watcher.py** - Public page scraping module that:
   - Monitors 5 sections: INFORMATION, BLOG, MOVIE, PHOTO, Q&A
   - Uses CSS selectors to extract content
   - Detects changes by comparing href links (not text content)
   - Persists state in snapshot.json

3. **member_watcher.py** - Member page monitoring module that:
   - Uses Playwright for browser automation
   - Handles login with PLUSMEMBER_ID and PLUSMEMBER_PASSWORD
   - Monitors member-exclusive sections
   - Manages session persistence in playwright_session.json
   - Maintains separate state in member_snapshot.json

## Key Implementation Details

- **Change Detection**: Uses href URLs as stable identifiers, ignoring text changes
- **Error Handling**: All errors are sent to DEV_CHANNEL_ID for monitoring
- **State Management**: JSON snapshot stored at project root
- **Twitter Integration**: Appends timestamps to URLs to bypass duplicate detection
- **Deployment**: Automated via GitHub Actions to Sakura server with systemd

## Environment Variables

Required in .env:
- DISCORD_TOKEN
- DISCORD_CHANNEL_ID (production notifications)
- DEV_CHANNEL_ID (error messages)
- Twitter API credentials (5 variables)
- PLUSMEMBER_ID (optional, for member page monitoring)
- PLUSMEMBER_PASSWORD (optional, for member page monitoring)

## Testing

Tests use unittest with mocking for HTTP requests and BeautifulSoup parsing. Run with proper PYTHONPATH to ensure module imports work correctly.

## Notes

- All user-facing messages and comments are in Japanese
- The bot monitors https://fc.hiyolab.com/ for updates
- CSS selectors in watcher.py are tailored to the specific site structure
- Member page monitoring requires Playwright and browser installation
- Session files (playwright_session.json, member_snapshot.json) are gitignored

## CSS Selectors and DOM Structure

- chat-area ul li div pのidがcomment-body-です