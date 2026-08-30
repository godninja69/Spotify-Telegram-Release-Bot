import sqlite3

class Database:
    def __init__(self, db_name="radar.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.setup()

    def setup(self):
        # Table to store tracked artists mapped to users
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS artists (
                spotify_id TEXT,
                name TEXT,
                chat_id INTEGER,
                PRIMARY KEY (spotify_id, chat_id)
            )
        ''')
        # Table to track releases we have already notified about
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS seen_releases (
                release_id TEXT PRIMARY KEY
            )
        ''')
        self.conn.commit()

    def add_artist(self, spotify_id, name, chat_id):
        try:
            self.cursor.execute(
                "INSERT INTO artists (spotify_id, name, chat_id) VALUES (?, ?, ?)",
                (spotify_id, name, chat_id)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False # Already tracking this artist

    def remove_artist(self, spotify_id, chat_id):
        self.cursor.execute(
            "DELETE FROM artists WHERE spotify_id = ? AND chat_id = ?",
            (spotify_id, chat_id)
        )
        self.conn.commit()

    def get_all_artists(self):
        self.cursor.execute("SELECT spotify_id, name, chat_id FROM artists")
        return self.cursor.fetchall()

    def get_user_artists(self, chat_id):
        self.cursor.execute("SELECT name FROM artists WHERE chat_id = ?", (chat_id,))
        return [row[0] for row in self.cursor.fetchall()]

    def is_release_seen(self, release_id):
        self.cursor.execute("SELECT 1 FROM seen_releases WHERE release_id = ?", (release_id,))
        return self.cursor.fetchone() is not None

    def mark_release_seen(self, release_id):
        self.cursor.execute(
            "INSERT OR IGNORE INTO seen_releases (release_id) VALUES (?)",
            (release_id,)
        )
        self.conn.commit()