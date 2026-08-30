# 🎧 Spotify Telegram Release Radar Bot

A lightweight, highly efficient Telegram bot that acts as your personal Spotify Release Radar. It scans your followed artists every 10 minutes and sends instant push notifications to your Telegram when a new album, single, or feature (`appears_on`) drops.

## ✨ Features
* **Lightning Fast:** Polls Spotify every 10 minutes for instant notifications.
* **Full Coverage:** Catches albums, singles, and collaborations/features.
* **Smart Database:** Built-in SQLite database prevents duplicate alerts and handles first-time imports gracefully.
* **Bulk Import:** Add multiple artists at once using comma-separated lists or by dropping `.txt`, `.csv`, or `.json` files directly into the Telegram chat.
* **Windows Automation:** Includes scripts to run the bot completely invisibly in the background.

## 📋 Prerequisites
1. **Python 3.8+** installed on your system.
2. A **Telegram Bot Token** (Get this from [@BotFather](https://t.me/botfather) on Telegram).
3. **Spotify API Keys** (Client ID and Client Secret). 
   * *Note: As of 2026, Spotify requires an active Premium subscription to generate Web API keys.*

## 🚀 Installation & Setup

**1. Clone the repository and navigate to the folder:**
```bash
git clone https://github.com/godninja69/Spotify-Telegram-Release-Bot.git
cd Spotify-Telegram-release-bot

2. Create and activate a virtual environment:
Bash

python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

3. Install dependencies:
Bash

pip install -r requirements.txt

4. Set up your environment variables:
Create a file named exactly .env in the root folder and add your keys:
Code snippet

BOT_TOKEN=your_telegram_bot_token
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

🤖 Bot Commands

Start a chat with your bot on Telegram and use the following commands:

    /start - Boot up the bot and view instructions.

    /add <link or name> - Track a single artist.

    /bulkadd <names/links> - Add multiple artists separated by commas or new lines.

    /list - View all tracked artists.

    /remove <name> - Stop tracking an artist.

    File Upload: Simply drag and drop a .txt, .csv, or .json file containing artist names or links into the chat to bulk-import them.

🪟 How to Run on Windows (Invisible & Auto-Start)

This repository includes two Windows scripts (start_bot.bat and hidden_bot.vbs) that allow you to run the bot silently in the background without keeping a terminal window open.

To run it silently:
Simply double-click hidden_bot.vbs. The bot will start in the background. To stop it, open Task Manager (Ctrl + Shift + Esc) and end the python.exe task.

To make it run automatically when you turn on your PC:

    Right-click hidden_bot.vbs and select Create shortcut.

    Press Win + R on your keyboard, type exactly shell:startup, and press Enter.

    A secret Windows Startup folder will open. Drag and drop the shortcut you just created into this folder.

    The bot will now silently launch in the background every time you start your computer!