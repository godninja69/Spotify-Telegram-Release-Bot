import os
import re
import json
import io
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from database import Database
from spotify_client import SpotifyEngine

load_dotenv()

db = Database()
spotify = SpotifyEngine()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎧 **Release Radar Bot Online**\n\n"
        "• `/add <name or link>` — Track a single artist\n"
        "• `/bulkadd <links/names separated by comma or new line>`\n"
        "• **Upload File:** Drop a `.txt`, `.csv`, or `.json` file to import artists\n"
        "• `/list` — View all tracked artists\n"
        "• `/remove <artist name>` — Unfollow an artist",
        parse_mode="Markdown",
    )


async def process_batch_import(
    queries: list, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Helper function to process multiple artist queries and provide real-time updates."""
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text(
        f"⏳ Processing {len(queries)} artists. Please wait..."
    )

    added = []
    already_tracked = []
    failed = []

    for query in queries:
        query = query.strip()
        if not query:
            continue

        artist = spotify.get_artist_info(query)
        if not artist:
            failed.append(query)
            continue

        if db.add_artist(artist["id"], artist["name"], chat_id):
            added.append(artist["name"])
            # Prime the baseline so older tracks aren't alerted
            current_releases = spotify.get_latest_releases(artist["id"])
            for release in current_releases:
                db.mark_release_seen(release["id"])
        else:
            already_tracked.append(artist["name"])

        # Brief pause to respect rate limits
        await asyncio.sleep(0.3)

    summary = (
        f"✅ **Import Complete!**\n\n"
        f"• **Added ({len(added)}):** {', '.join(added) if added else 'None'}\n"
    )
    if already_tracked:
        summary += f"• **Already Tracked ({len(already_tracked)}):** {', '.join(already_tracked)}\n"
    if failed:
        summary += f"• **Failed / Not Found ({len(failed)}):** {', '.join(failed)}\n"

    # Telegram message limit is 4096 characters; truncate safely if list is huge
    if len(summary) > 4000:
        summary = summary[:3900] + "\n\n...[Truncated due to Telegram limit]"

    await status_msg.edit_text(summary, parse_mode="Markdown")


async def add_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Please provide a Spotify artist link or name.\nExample: `/add Lauv`",
            parse_mode="Markdown",
        )
        return

    query = " ".join(context.args)
    chat_id = update.effective_chat.id
    artist = spotify.get_artist_info(query)

    if not artist:
        await update.message.reply_text("❌ Could not find that artist on Spotify.")
        return

    if db.add_artist(artist["id"], artist["name"], chat_id):
        await update.message.reply_text(
            f"✅ Now tracking: **{artist['name']}**", parse_mode="Markdown"
        )
        current_releases = spotify.get_latest_releases(artist["id"])
        for release in current_releases:
            db.mark_release_seen(release["id"])
    else:
        await update.message.reply_text(
            f"⚠️ You are already tracking **{artist['name']}**.", parse_mode="Markdown"
        )


async def bulk_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Please provide links or names separated by commas or new lines.\n"
            "Example:\n`/bulkadd Lauv, Ed Sheeran, https://open.spotify.com/artist/...`",
            parse_mode="Markdown",
        )
        return

    raw_text = update.message.text.partition(" ")[2]  # Everything after "/bulkadd "
    # Split by commas or newlines
    queries = [q.strip() for q in re.split(r"[,\n]+", raw_text) if q.strip()]
    await process_batch_import(queries, update, context)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parses .txt, .csv, or .json files sent directly to the bot."""
    doc = update.message.document
    filename = doc.file_name.lower()

    if not (
        filename.endswith(".txt")
        or filename.endswith(".csv")
        or filename.endswith(".json")
    ):
        await update.message.reply_text(
            "❌ Please upload a `.txt`, `.csv`, or `.json` file."
        )
        return

    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()
    content = file_bytes.decode("utf-8", errors="ignore")

    queries = []
    if filename.endswith(".json"):
        try:
            data = json.loads(content)
            # Handles Spotify GDPR Follow.json format
            if isinstance(data, dict) and "artists" in data:
                queries = [
                    item.get("name") or item.get("uri")
                    for item in data["artists"]
                    if item
                ]
            # Handles list format [{"name": "..."}, ...] or ["name1", "name2"]
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        queries.append(
                            item.get("name") or item.get("uri") or item.get("url")
                        )
                    elif isinstance(item, str):
                        queries.append(item)
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to parse JSON file: {e}")
            return
    else:
        # For .txt and .csv, parse line by line or comma-separated
        queries = [
            line.strip() for line in re.split(r"[\r\n,]+", content) if line.strip()
        ]

    if not queries:
        await update.message.reply_text("❌ No artists found in that file.")
        return

    await process_batch_import(queries, update, context)


async def list_artists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    artists = db.get_user_artists(update.effective_chat.id)
    if not artists:
        await update.message.reply_text("You aren't tracking any artists yet.")
        return

    artist_lines = [f"• {name}" for name in sorted(artists)]
    message = f"📋 **Tracked Artists ({len(artists)}):**\n\n" + "\n".join(artist_lines)

    # Split into chunks if message exceeds Telegram limit
    if len(message) > 4000:
        for chunk in [message[i : i + 3800] for i in range(0, len(message), 3800)]:
            await update.message.reply_text(chunk, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")


async def remove_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/remove <exact artist name>`", parse_mode="Markdown"
        )
        return

    target = " ".join(context.args).strip().lower()
    chat_id = update.effective_chat.id
    all_artists = db.get_all_artists()

    found = None
    for spotify_id, name, user_id in all_artists:
        if user_id == chat_id and name.lower() == target:
            found = (spotify_id, name)
            break

    if found:
        db.remove_artist(found[0], chat_id)
        await update.message.reply_text(
            f"🗑️ Removed **{found[1]}** from tracking.", parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Artist not found in your tracking list.")


async def check_spotify_releases(context: ContextTypes.DEFAULT_TYPE):
    """Runs every 10 minutes to scan for new drops."""
    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scanning Spotify for new releases..."
    )
    all_artists = db.get_all_artists()

    for spotify_id, artist_name, chat_id in all_artists:
        releases = spotify.get_latest_releases(spotify_id)

        for release in releases:
            if not db.is_release_seen(release["id"]):
                db.mark_release_seen(release["id"])

                try:
                    release_year = int(release["release_date"].split("-")[0])
                    current_year = datetime.now().year
                    if release_year >= current_year - 1:
                        message = (
                            f"🚨 **NEW {release['type'].upper()} DROP!**\n\n"
                            f"👤 **Artist:** {artist_name}\n"
                            f"🎵 **Title:** {release['name']}\n"
                            f"🔗 **Link:** {release['url']}"
                        )
                        await context.bot.send_message(
                            chat_id=chat_id, text=message, parse_mode="Markdown"
                        )
                except Exception as e:
                    print(f"Date parse error: {e}")

        await asyncio.sleep(0.3)


if __name__ == "__main__":
    bot_token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(bot_token).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_artist))
    app.add_handler(CommandHandler("bulkadd", bulk_add))
    app.add_handler(CommandHandler("list", list_artists))
    app.add_handler(CommandHandler("remove", remove_artist))

    # File uploads
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Recurring background check every 10 minutes (600 seconds)
    job_queue = app.job_queue
    job_queue.run_repeating(check_spotify_releases, interval=600, first=10)

    print("Bot is starting up with bulk add & file upload support...")
    app.run_polling()
