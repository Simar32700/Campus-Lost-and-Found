import sqlite3
import contextlib
from config import DATABASE_PATH

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextlib.contextmanager
def get_db():
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'USER',
                phone TEXT,
                created_at TEXT NOT NULL
            )
        """)

        # 2. Items Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL, -- 'LOST' or 'FOUND'
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT NOT NULL,
                item_date TEXT NOT NULL,
                image_url TEXT,
                status TEXT NOT NULL DEFAULT 'OPEN', -- 'OPEN', 'MATCHED', 'CLOSED'
                reporter_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(reporter_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 3. Matches Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id TEXT PRIMARY KEY,
                lost_item_id TEXT NOT NULL,
                found_item_id TEXT NOT NULL,
                score REAL NOT NULL,
                breakdown TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'REJECTED'
                admin_id TEXT,
                reviewed_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(lost_item_id) REFERENCES items(id) ON DELETE CASCADE,
                FOREIGN KEY(found_item_id) REFERENCES items(id) ON DELETE CASCADE,
                FOREIGN KEY(admin_id) REFERENCES users(id) ON DELETE SET NULL,
                UNIQUE(lost_item_id, found_item_id)
            )
        """)

        # 4. Chat Rooms Table (unlocked upon match approval)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_rooms (
                id TEXT PRIMARY KEY,
                match_id TEXT UNIQUE NOT NULL,
                lost_reporter_id TEXT NOT NULL,
                found_reporter_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                dismissed_by TEXT,
                dismissed_at TEXT,
                resolve_lost_confirmed INTEGER NOT NULL DEFAULT 0,
                resolve_found_confirmed INTEGER NOT NULL DEFAULT 0,
                resolved_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE,
                FOREIGN KEY(lost_reporter_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(found_reporter_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("PRAGMA table_info(chat_rooms)")
        chat_columns = {row["name"] for row in cursor.fetchall()}
        if "status" not in chat_columns:
            cursor.execute("ALTER TABLE chat_rooms ADD COLUMN status TEXT NOT NULL DEFAULT 'OPEN'")
        if "dismissed_by" not in chat_columns:
            cursor.execute("ALTER TABLE chat_rooms ADD COLUMN dismissed_by TEXT")
        if "dismissed_at" not in chat_columns:
            cursor.execute("ALTER TABLE chat_rooms ADD COLUMN dismissed_at TEXT")
        if "resolve_lost_confirmed" not in chat_columns:
            cursor.execute("ALTER TABLE chat_rooms ADD COLUMN resolve_lost_confirmed INTEGER NOT NULL DEFAULT 0")
        if "resolve_found_confirmed" not in chat_columns:
            cursor.execute("ALTER TABLE chat_rooms ADD COLUMN resolve_found_confirmed INTEGER NOT NULL DEFAULT 0")
        if "resolved_at" not in chat_columns:
            cursor.execute("ALTER TABLE chat_rooms ADD COLUMN resolved_at TEXT")

        # 5. Messages Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_room_id TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                content TEXT NOT NULL,
                attachment_url TEXT,
                attachment_type TEXT,
                attachment_name TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(chat_room_id) REFERENCES chat_rooms(id) ON DELETE CASCADE,
                FOREIGN KEY(sender_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        cursor.execute("PRAGMA table_info(messages)")
        message_columns = {row["name"] for row in cursor.fetchall()}
        if "attachment_url" not in message_columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN attachment_url TEXT")
        if "attachment_type" not in message_columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN attachment_type TEXT")
        if "attachment_name" not in message_columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN attachment_name TEXT")

        # Indexes for fast lookup
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_type_status ON items(type, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_reporter ON items(reporter_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_room ON messages(chat_room_id)")
