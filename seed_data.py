import uuid
import datetime
from database import get_db
from auth import hash_password
from matching import evaluate_item_matches

def seed_initial_data(force: bool = False):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM users")
        if cursor.fetchone()["cnt"] > 0 and not force:
            print("[INFO] Database already contains data. Skipping initial seeding.")
            return

        print("[INFO] Seeding prototype database with realistic campus demo data...")

        # 1. Seed Users
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        users_data = [
            ("user-admin-001", "admin@campus.edu", hash_password("Admin@123"), "Campus Security Admin", "ADMIN", "555-0100", now),
            ("user-alex-002", "alex.chen@campus.edu", hash_password("Student@123"), "Alex Chen", "USER", "555-0101", now),
            ("user-priya-003", "priya.patel@campus.edu", hash_password("Student@123"), "Priya Patel", "USER", "555-0102", now),
            ("user-marcus-004", "marcus.johnson@campus.edu", hash_password("Student@123"), "Marcus Johnson", "USER", "555-0103", now),
        ]

        cursor.executemany(
            """
            INSERT OR REPLACE INTO users (id, email, password_hash, full_name, role, phone, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            users_data
        )

        # 2. Seed Items
        items_data = [
            # Lost 1: Alex's MacBook
            (
                "item-lost-001", "LOST",
                "Space Gray MacBook Pro 14 inch M2",
                "Electronics",
                "Left my 14-inch Space Gray MacBook Pro with a black protective sleeve and a sticker on the lid.",
                "Central Library 2nd Floor Study Desks",
                "2026-09-10",
                "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?auto=format&fit=crop&w=600&q=80",
                "OPEN", "user-alex-002", now
            ),
            # Found 1: Priya found MacBook (will match with Lost 1 >= 80%)
            (
                "item-found-001", "FOUND",
                "Apple MacBook Pro 14 inch Space Gray",
                "Electronics",
                "Found a Space Gray 14-inch MacBook Pro inside a black protective sleeve left on desk #18.",
                "Central Library 2nd Floor",
                "2026-09-10",
                "https://images.unsplash.com/photo-1541807084-5c52b6b3adef?auto=format&fit=crop&w=600&q=80",
                "OPEN", "user-priya-003", now
            ),
            # Lost 2: Marcus lost Hydro Flask
            (
                "item-lost-002", "LOST",
                "Cobalt Blue Hydro Flask 32oz Bottle",
                "Accessories",
                "Cobalt blue insulated Hydro Flask water bottle with campus stickers and a silver carabiner.",
                "Campus Recreation Center Gym Bleachers",
                "2026-09-11",
                "https://images.unsplash.com/photo-1602143407151-7111542de6e8?auto=format&fit=crop&w=600&q=80",
                "OPEN", "user-marcus-004", now
            ),
            # Found 2: Priya found Hydro Flask (will match with Lost 2 >= 80%)
            (
                "item-found-002", "FOUND",
                "Blue Hydro Flask Water Bottle Insulated",
                "Accessories",
                "Found a blue Hydro Flask 32oz bottle with stickers near the indoor basketball court bleachers.",
                "Campus Recreation Center Gym",
                "2026-09-11",
                "https://images.unsplash.com/photo-1544816155-12df9643f363?auto=format&fit=crop&w=600&q=80",
                "OPEN", "user-priya-003", now
            ),
            # Lost 3: Alex lost wallet
            (
                "item-lost-003", "LOST",
                "Brown Leather Bi-fold Wallet with College ID",
                "ID Cards",
                "Brown leather Tommy Hilfiger wallet containing college student ID for Alex Chen and debit cards.",
                "Dining Commons Dining Hall B",
                "2026-09-09",
                "https://images.unsplash.com/photo-1627123424574-724758594e93?auto=format&fit=crop&w=600&q=80",
                "OPEN", "user-alex-002", now
            ),
            # Found 3: Marcus found Sony Headphones
            (
                "item-found-003", "FOUND",
                "Sony WH-1000XM4 Noise Canceling Headphones",
                "Electronics",
                "Black over-ear Sony noise-canceling headphones inside their gray zippered travel case.",
                "Campus Quad Lawn Bench",
                "2026-09-11",
                "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=600&q=80",
                "OPEN", "user-marcus-004", now
            )
        ]

        cursor.executemany(
            """
            INSERT OR REPLACE INTO items (id, type, title, category, description, location, item_date, image_url, status, reporter_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            items_data
        )

    # 3. Trigger matching engine for items so matches table has high-confidence candidates ready
    for item in ["item-lost-001", "item-found-001", "item-lost-002", "item-found-002"]:
        evaluate_item_matches(item)

    print("[SUCCESS] Prototype database initialized with test users, sample items, and pending matches!")

if __name__ == "__main__":
    from database import init_db
    init_db()
    seed_initial_data(force=True)
