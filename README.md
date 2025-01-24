# Simple Telegram Media Bot

## Setup in Termux

1. Install required packages:
```bash
pkg update && pkg upgrade
pkg install python gallery-dl ffmpeg
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Create a file named `links.txt` in the same directory.

4. Run the bot:
```bash
python bot.py
```

## Usage

1. Add links to `links.txt`, one per line
2. The bot will automatically process the links
3. Media will be downloaded, text overlay will be added, and sent to the specified Telegram chat
4. Files are automatically deleted after sending

## Features

- Adds centered text overlay to media files
- Automatically downloads media from supported platforms
- Sends media to Telegram with 30-second intervals
- Cleans up files after sending

## Notes

- The bot waits 30 seconds between sends to avoid rate limits
- Make sure you have enough storage space in Termux
- Keep your phone charged and connected to the internet
- FFmpeg is used for adding text overlay to media files