import os
import re
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from database import Database
from spotify_client import SpotifyEngine

# Load environment variables from .env
load_dotenv()

# Initialize the database and Spotify API client
db = Database()
spotify = SpotifyEngine()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the welcome message and command list."""
    await update.message.reply_text(
        "🎧 **Release Radar Bot Online**\n\n"
        "• `/add <name or link>` — Track a single artist\n"
        "• `/bulkadd <names/links>` — Track multiple artists at once\n"
        "• **Upload File:** Drop a `.txt`, `.csv`, or `.json` file to import artists\n"
        "• `/list` — View all tracked artists\n"
        "• `/remove <name or link>` — Unfollow an artist (partial names work!)\n"
        "• `/bulkremove <names>` — Unfollow multiple artists",
        parse_mode='Markdown'
    )

async def process_batch_import(queries: list, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Helper function to process multiple artist queries and provide real-time updates."""
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text(f"⏳ Processing {len(queries)} artists. Please wait...")

    added = []
    already_tracked = []
    failed = []

    for query in queries:
        query = query.strip()
        if not query:
            continue

        # Fetch from Spotify
        artist = spotify.get_artist_info(query)
        if not artist:
            failed.append(query)
            continue

        # Add to database
        if db.add_artist(artist['id'], artist['name'], chat_id):
            added.append(artist['name'])
            # Prime the baseline so older tracks aren't alerted
            current_releases = spotify.get_latest_releases(artist['id'])
            for release in current_releases:
                db.mark_release_seen(release['id'])
        else:
            already_tracked.append(artist['name'])

        # Brief pause to respect Spotify's API rate limits
        await asyncio.sleep(0.3)

    # Build the summary text
    summary = (
        f"✅ **Import Complete!**\n\n"
        f"• **Added ({len(added)}):** {', '.join(added) if added else 'None'}\n"
    )
    if already_tracked:
        summary += f"• **Already Tracked ({len(already_tracked)}):** {', '.join(already_tracked)}\n"
    if failed:
        summary += f"• **Failed / Not Found ({len(failed)}):**\n" + "\n".join(failed)

    # Telegram message limit is 4096 characters; truncate safely if list is huge
    if len(summary) > 4000:
        summary = summary[:3900] + "\n\n...[Truncated due to Telegram character limit]"

    await status_msg.edit_text(summary, parse_mode='Markdown', disable_web_page_preview=True)

async def add_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a single artist to the tracking list."""
    if not context.args:
        await update.message.reply_text("Please provide a Spotify artist link or name.\nExample: `/add Lauv`", parse_mode='Markdown')
        return

    query = " ".join(context.args)
    chat_id = update.effective_chat.id
    artist = spotify.get_artist_info(query)

    if not artist:
        await update.message.reply_text("❌ Could not find that artist on Spotify.")
        return

    if db.add_artist(artist['id'], artist['name'], chat_id):
        await update.message.reply_text(f"✅ Now tracking: **{artist['name']}**", parse_mode='Markdown')
        current_releases = spotify.get_latest_releases(artist['id'])
        for release in current_releases:
            db.mark_release_seen(release['id'])
    else:
        await update.message.reply_text(f"⚠️ You are already tracking **{artist['name']}**.", parse_mode='Markdown')

async def bulk_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds multiple artists from a text message, dynamically splitting links and spaces."""
    # Strip the exact "/bulkadd" command from the beginning of the text
    raw_text = re.sub(r'^/bulkadd(?:@\w+)?\s*', '', update.message.text, flags=re.IGNORECASE)

    if not raw_text.strip():
        await update.message.reply_text(
            "Please provide links or names separated by commas or new lines.\n"
            "Example:\n`/bulkadd Lauv, Ed Sheeran`\nOr paste multiple links.",
            parse_mode='Markdown'
        )
        return

    # THE FIX: If links are pasted with spaces between them instead of newlines,
    # or mashed together (https://...https://...), force a newline before every "https://"
    raw_text = re.sub(r'(?<!^)(https://)', r'\n\1', raw_text)

    # Split by commas, newlines, or tabs
    queries = [q.strip() for q in re.split(r'[\r\n,\t]+', raw_text) if q.strip()]
    await process_batch_import(queries, update, context)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parses .txt, .csv, or .json files sent directly to the bot for bulk import."""
    doc = update.message.document
    filename = doc.file_name.lower()

    if not (filename.endswith('.txt') or filename.endswith('.csv') or filename.endswith('.json')):
        await update.message.reply_text("❌ Please upload a `.txt`, `.csv`, or `.json` file.")
        return

    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()
    content = file_bytes.decode('utf-8', errors='ignore')

    queries = []
    if filename.endswith('.json'):
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "artists" in data:
                queries = [item.get('name') or item.get('uri') for item in data["artists"] if item]
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        queries.append(item.get('name') or item.get('uri') or item.get('url'))
                    elif isinstance(item, str):
                        queries.append(item)
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to parse JSON file: {e}")
            return
    else:
        # For text files, apply the same smart link-splitting fix
        content = re.sub(r'(?<!^)(https://)', r'\n\1', content)
        queries = [line.strip() for line in re.split(r'[\r\n,]+', content) if line.strip()]

    if not queries:
        await update.message.reply_text("❌ No valid artists found in that file.")
        return

    await process_batch_import(queries, update, context)

async def list_artists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists all currently tracked artists for the user."""
    artists = db.get_user_artists(update.effective_chat.id)
    if not artists:
        await update.message.reply_text("You aren't tracking any artists yet.")
        return

    artist_lines = [f"• {name}" for name in sorted(artists)]
    message = f"📋 **Tracked Artists ({len(artists)}):**\n\n" + "\n".join(artist_lines)
    
    # Split into chunks if message exceeds Telegram limit
    if len(message) > 4000:
        for chunk in [message[i:i+3800] for i in range(0, len(message), 3800)]:
            await update.message.reply_text(chunk, parse_mode='Markdown')
    else:
        await update.message.reply_text(message, parse_mode='Markdown')

async def remove_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Smarter remove command that supports partial name matching and Spotify links."""
    if not context.args:
        await update.message.reply_text("Usage: `/remove <artist name, keyword, or link>`", parse_mode='Markdown')
        return

    raw_query = " ".join(context.args).strip()
    chat_id = update.effective_chat.id
    
    # Try to extract an ID if the user pasted a Spotify link
    match = re.search(r'artist/([a-zA-Z0-9]+)', raw_query)
    artist_id = match.group(1) if match else None

    all_artists = db.get_all_artists()
    user_artists = [a for a in all_artists if a[2] == chat_id]

    removed = []
    if artist_id:
        for s_id, name, _ in user_artists:
            if s_id == artist_id:
                db.remove_artist(s_id, chat_id)
                removed.append(name)
                break
    else:
        # Do a partial, case-insensitive match against the saved names
        target = raw_query.lower()
        for s_id, name, _ in user_artists:
            if target in name.lower():
                db.remove_artist(s_id, chat_id)
                removed.append(name)

    if removed:
        await update.message.reply_text(f"🗑️ Removed: **{', '.join(removed)}**", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"❌ No matching artist found for `{raw_query}` in your list.", parse_mode='Markdown')

async def bulk_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Removes multiple artists simultaneously using partial matching."""
    raw_text = re.sub(r'^/bulkremove(?:@\w+)?\s*', '', update.message.text, flags=re.IGNORECASE)
    
    if not raw_text.strip():
        await update.message.reply_text("Usage: `/bulkremove Name 1, Name 2, Name 3`", parse_mode='Markdown')
        return

    targets = [t.strip().lower() for t in re.split(r'[,\n]+', raw_text) if t.strip()]
    chat_id = update.effective_chat.id

    all_artists = db.get_all_artists()
    user_artists = [a for a in all_artists if a[2] == chat_id]

    removed = []
    for s_id, name, _ in user_artists:
        for t in targets:
            if t in name.lower():
                db.remove_artist(s_id, chat_id)
                removed.append(name)
                break # Break inner loop if removed, move to next saved artist

    if removed:
        await update.message.reply_text(f"🗑️ Bulk Removed ({len(removed)}):\n• " + "\n• ".join(removed))
    else:
        await update.message.reply_text("❌ None of those artists were found in your tracking list.")

async def check_spotify_releases(context: ContextTypes.DEFAULT_TYPE):
    """Background task that runs every 10 minutes to scan for new drops."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scanning Spotify for new releases...")
    all_artists = db.get_all_artists()

    for spotify_id, artist_name, chat_id in all_artists:
        try:
            releases = spotify.get_latest_releases(spotify_id)

            for release in releases:
                if not db.is_release_seen(release['id']):
                    db.mark_release_seen(release['id'])

                    # Only notify for relatively recent releases to avoid spam on initial startup
                    try:
                        release_year = int(release['release_date'].split('-')[0])
                        current_year = datetime.now().year
                        
                        if release_year >= current_year - 1:
                            message = (
                                f"🚨 **NEW {release['type'].upper()} DROP!**\n\n"
                                f"👤 **Artist:** {artist_name}\n"
                                f"🎵 **Title:** {release['name']}\n"
                                f"🔗 **Link:** {release['url']}"
                            )
                            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')
                    except Exception as e:
                        print(f"Date parse error for {release['name']}: {e}")

        except Exception as e:
            print(f"Failed to check releases for {artist_name}: {e}")

        # Sleep briefly to avoid slamming the Spotify API
        await asyncio.sleep(0.3)

if __name__ == '__main__':
    # Initialize Bot
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        print("CRITICAL ERROR: BOT_TOKEN not found in .env file.")
        exit(1)
        
    app = ApplicationBuilder().token(bot_token).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_artist))
    app.add_handler(CommandHandler("bulkadd", bulk_add))
    app.add_handler(CommandHandler("list", list_artists))
    app.add_handler(CommandHandler("remove", remove_artist))
    app.add_handler(CommandHandler("bulkremove", bulk_remove))

    # File uploads (.txt, .csv, .json)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Recurring background check every 10 minutes (600 seconds)
    job_queue = app.job_queue
    job_queue.run_repeating(check_spotify_releases, interval=600, first=10)

    print("Bot is starting up with advanced link detection and bulk controls...")
    app.run_polling()