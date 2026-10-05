import re
import json
import uuid
import datetime
from difflib import SequenceMatcher
from functools import lru_cache
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics.pairwise import cosine_similarity
from config import (
    MATCH_CONFIDENCE_THRESHOLD,
)
from database import get_db

STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "by", "for", "with",
    "about", "against", "between", "into", "through", "during", "before",
    "after", "above", "below", "to", "from", "up", "down", "is", "was", "are",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "i", "my", "me", "we", "our", "you", "your", "he", "she", "it", "they",
    "this", "that", "these", "those", "lost", "found", "item", "please", "help"
}

SYNONYMS = {
    "cellphone": "phone",
    "mobile": "phone",
    "smartphone": "phone",
    "earphones": "earbuds",
    "airpods": "earbuds",
    "mac": "macbook",
    "laptop": "computer",
    "notebook": "computer",
    "spectacles": "glasses",
    "specs": "glasses",
    "bottle": "waterbottle",
    "flask": "waterbottle",
    "id": "identity",
    "card": "card",
    "wallet": "wallet",
    "keys": "key",
}

PLACE_KEYWORDS = {
    "library", "gym", "hall", "cafeteria", "canteen", "lab", "quad",
    "dorm", "hostel", "building", "classroom", "auditorium", "parking",
    "mess", "office", "desk", "gate"
}

def normalize_text(text: str) -> str:
    if not text:
        return ""
    words = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
    return " ".join(SYNONYMS.get(word, word) for word in words)

def clean_and_tokenize(text: str) -> set[str]:
    if not text:
        return set()
    words = normalize_text(text).split()
    return {w for w in words if w not in STOPWORDS and len(w) > 1}

def calculate_jaccard(tokens1: set[str], tokens2: set[str]) -> float:
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union) if union else 0.0

def calculate_text_similarity(str1: str, str2: str) -> float:
    if not str1 or not str2:
        return 0.0
    t1 = clean_and_tokenize(str1)
    t2 = clean_and_tokenize(str2)
    jaccard = calculate_jaccard(t1, t2)
    
    # Also calculate fuzzy string ratio to catch minor typos / variations
    seq_ratio = SequenceMatcher(None, str1.lower().strip(), str2.lower().strip()).ratio()
    
    # Blend jaccard token overlap (65%) and character sequence ratio (35%)
    return (0.65 * jaccard) + (0.35 * seq_ratio)

def calculate_ai_text_similarity(str1: str, str2: str) -> float:
    """
    Uses a local TF-IDF vector model to compare meaning-bearing words.
    This is lightweight ML-based matching and does not require an external AI API.
    """
    str1 = normalize_text(str1)
    str2 = normalize_text(str2)
    if not str1 or not str2:
        return 0.0

    try:
        vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words=list(STOPWORDS),
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b[a-zA-Z0-9_-]+\b"
        )
        vectors = vectorizer.fit_transform([str1, str2])
        return float(cosine_similarity(vectors[0], vectors[1])[0][0])
    except ValueError:
        return calculate_text_similarity(str1, str2)

def blend_text_scores(str1: str, str2: str) -> float:
    ai_score = calculate_ai_text_similarity(str1, str2)
    fuzzy_score = calculate_text_similarity(str1, str2)
    tokens1 = clean_and_tokenize(str1)
    tokens2 = clean_and_tokenize(str2)
    token_overlap = calculate_jaccard(tokens1, tokens2)
    containment = 0.0
    if tokens1 and tokens2:
        containment = len(tokens1.intersection(tokens2)) / min(len(tokens1), len(tokens2))
    return (0.40 * ai_score) + (0.30 * fuzzy_score) + (0.30 * max(token_overlap, containment))

def calculate_date_similarity(date1: str, date2: str) -> float:
    try:
        d1 = datetime.date.fromisoformat((date1 or "").strip()[:10])
        d2 = datetime.date.fromisoformat((date2 or "").strip()[:10])
    except ValueError:
        return 0.5 if not date1 or not date2 else 0.0

    days = abs((d1 - d2).days)
    if days == 0:
        return 1.0
    if days <= 1:
        return 0.85
    if days <= 3:
        return 0.65
    if days <= 7:
        return 0.35
    return 0.0

def calculate_description_evidence(lost_item: dict, found_item: dict) -> dict:
    lost_text = " ".join([
        lost_item.get("title") or "",
        lost_item.get("description") or "",
    ])
    found_text = " ".join([
        found_item.get("title") or "",
        found_item.get("description") or "",
    ])

    lost_tokens = clean_and_tokenize(lost_text)
    found_tokens = clean_and_tokenize(found_text)
    if not lost_tokens or not found_tokens:
        return {"shared_count": 0, "containment": 0.0, "shared_terms": []}

    shared_tokens = lost_tokens.intersection(found_tokens)
    containment = len(shared_tokens) / min(len(lost_tokens), len(found_tokens))

    return {
        "shared_count": len(shared_tokens),
        "containment": containment,
        "shared_terms": sorted(shared_tokens)[:12]
    }

def extract_match_features(lost_item: dict, found_item: dict) -> tuple[list[float], dict]:
    cat_lost = (lost_item.get("category") or "").strip().lower()
    cat_found = (found_item.get("category") or "").strip().lower()
    if cat_lost == cat_found:
        category_score = 1.0
    elif cat_lost and cat_found and (cat_lost in cat_found or cat_found in cat_lost):
        category_score = 0.6
    else:
        category_score = 0.0

    title_score = blend_text_scores(lost_item.get("title") or "", found_item.get("title") or "")
    description_score = blend_text_scores(lost_item.get("description") or "", found_item.get("description") or "")

    loc_lost = lost_item.get("location") or ""
    loc_found = found_item.get("location") or ""
    location_score = blend_text_scores(loc_lost, loc_found)
    loc_tokens_lost = clean_and_tokenize(loc_lost)
    loc_tokens_found = clean_and_tokenize(loc_found)
    shared_place = bool(loc_tokens_lost.intersection(loc_tokens_found).intersection(PLACE_KEYWORDS))
    if shared_place:
        location_score = max(location_score, 0.85)

    date_score = calculate_date_similarity(lost_item.get("item_date") or "", found_item.get("item_date") or "")
    evidence = calculate_description_evidence(lost_item, found_item)
    shared_term_score = min(evidence["shared_count"] / 8.0, 1.0)

    features = [
        category_score,
        title_score,
        description_score,
        location_score,
        date_score,
        shared_term_score,
        evidence["containment"],
        1.0 if shared_place else 0.0,
    ]

    breakdown = {
        "category_score": round(category_score * 100, 1),
        "title_score": round(title_score * 100, 1),
        "description_score": round(description_score * 100, 1),
        "location_score": round(location_score * 100, 1),
        "title_nlp_score": round(title_score * 100, 1),
        "description_nlp_score": round(description_score * 100, 1),
        "location_nlp_score": round(location_score * 100, 1),
        "date_score": round(date_score * 100, 1),
        "shared_description_terms": evidence["shared_terms"],
        "shared_term_count": evidence["shared_count"],
        "shared_term_coverage": round(evidence["containment"] * 100, 1),
        "shared_place_detected": shared_place,
    }

    return features, breakdown

@lru_cache(maxsize=1)
def get_match_classifier() -> GradientBoostingClassifier:
    """
    Tree-based ML classifier over NLP similarity features.
    It is trained from labelled prototype feature examples so the app can run locally.
    """
    training_rows = [
        [1.0, 0.85, 0.85, 0.90, 1.00, 1.00, 0.85, 1.0],
        [1.0, 0.65, 0.75, 0.85, 0.85, 0.80, 0.65, 1.0],
        [1.0, 0.50, 0.70, 0.80, 0.65, 0.70, 0.55, 1.0],
        [1.0, 0.70, 0.60, 0.25, 0.85, 0.65, 0.50, 0.0],
        [1.0, 0.40, 0.80, 0.75, 1.00, 0.75, 0.60, 1.0],
        [0.6, 0.75, 0.75, 0.85, 0.85, 0.85, 0.65, 1.0],
        [1.0, 0.20, 0.20, 0.90, 1.00, 0.20, 0.15, 1.0],
        [1.0, 0.10, 0.15, 0.00, 0.35, 0.10, 0.08, 0.0],
        [1.0, 0.45, 0.20, 0.85, 1.00, 0.25, 0.20, 1.0],
        [0.0, 0.80, 0.75, 0.85, 1.00, 0.80, 0.70, 1.0],
        [0.0, 0.10, 0.10, 0.90, 1.00, 0.10, 0.05, 1.0],
        [1.0, 0.35, 0.35, 0.10, 0.00, 0.35, 0.25, 0.0],
        [1.0, 0.05, 0.05, 0.00, 0.00, 0.05, 0.03, 0.0],
        [0.6, 0.25, 0.30, 0.85, 0.85, 0.25, 0.20, 1.0],
    ]
    labels = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    model = GradientBoostingClassifier(random_state=42)
    model.fit(training_rows, labels)
    return model

def calculate_match_score(lost_item: dict, found_item: dict) -> tuple[float, dict]:
    """
    Computes an ML/NLP confidence score (0 - 100) between a lost item and a found item.
    Returns (total_score, breakdown_dict).
    """
    features, breakdown = extract_match_features(lost_item, found_item)
    model = get_match_classifier()
    model_probability = float(model.predict_proba([features])[0][1])

    nlp_score = (
        (0.15 * features[0]) +
        (0.20 * features[1]) +
        (0.35 * features[2]) +
        (0.15 * features[3]) +
        (0.05 * features[4]) +
        (0.10 * max(features[5], features[6]))
    )

    total_score = ((0.65 * model_probability) + (0.35 * nlp_score)) * 100.0

    if features[0] == 0.0 and max(features[1], features[2]) < 0.90:
        total_score = min(total_score, 65.0)

    total_score = round(min(100.0, max(0.0, total_score)), 1)

    breakdown.update({
        "model": "GradientBoostingClassifier + TF-IDF NLP features",
        "ai_model_probability": round(model_probability * 100, 1),
        "nlp_weighted_score": round(nlp_score * 100, 1),
        "threshold": MATCH_CONFIDENCE_THRESHOLD,
        "is_match": total_score >= MATCH_CONFIDENCE_THRESHOLD
    })

    return total_score, breakdown

def open_chat_for_confirmed_match(cursor, match_id: str, lost: dict, found: dict, now: str) -> str:
    """
    Opens the recovery chat immediately for a high-confidence automatic match.
    """
    cursor.execute("UPDATE matches SET status = 'APPROVED', reviewed_at = ? WHERE id = ?", (now, match_id))
    cursor.execute("UPDATE items SET status = 'MATCHED' WHERE id IN (?, ?)", (lost["id"], found["id"]))

    cursor.execute("SELECT id FROM chat_rooms WHERE match_id = ?", (match_id,))
    existing_chat = cursor.fetchone()
    if existing_chat:
        return existing_chat["id"]

    chat_room_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO chat_rooms (id, match_id, lost_reporter_id, found_reporter_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (chat_room_id, match_id, lost["reporter_id"], found["reporter_id"], now)
    )

    msg_id = str(uuid.uuid4())
    initial_msg = (
        f"Item found! This lost report matched '{found['title']}' with "
        f"{MATCH_CONFIDENCE_THRESHOLD:.0f}% or higher confidence. You can now chat here "
        "to coordinate the return or handover."
    )
    cursor.execute(
        """
        INSERT INTO messages (id, chat_room_id, sender_id, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (msg_id, chat_room_id, lost["reporter_id"], initial_msg, now)
    )

    return chat_room_id

def evaluate_item_matches(item_id: str) -> list[dict]:
    """
    Evaluates an item against candidate items of the opposite type.
    Automatically opens chat for scores >= MATCH_CONFIDENCE_THRESHOLD (80%).
    """
    created_matches = []
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        current_item = cursor.fetchone()
        if not current_item or current_item["status"] != "OPEN":
            return []

        item_dict = dict(current_item)
        item_type = item_dict["type"]
        opposite_type = "FOUND" if item_type == "LOST" else "LOST"

        # Find open candidate items of opposite type
        cursor.execute(
            "SELECT * FROM items WHERE type = ? AND status = 'OPEN' AND reporter_id != ?",
            (opposite_type, item_dict["reporter_id"])
        )
        candidates = [dict(row) for row in cursor.fetchall()]

        for candidate in candidates:
            if item_type == "LOST":
                lost = item_dict
                found = candidate
            else:
                lost = candidate
                found = item_dict

            score, breakdown = calculate_match_score(lost, found)

            if score >= MATCH_CONFIDENCE_THRESHOLD:
                # Check if match record already exists
                cursor.execute(
                    "SELECT id, status FROM matches WHERE lost_item_id = ? AND found_item_id = ?",
                    (lost["id"], found["id"])
                )
                existing = cursor.fetchone()
                now = datetime.datetime.now(datetime.timezone.utc).isoformat()

                if existing:
                    match_id = existing["id"]
                    if existing["status"] == "REJECTED":
                        continue
                else:
                    match_id = str(uuid.uuid4())
                    cursor.execute(
                        """
                        INSERT INTO matches (id, lost_item_id, found_item_id, score, breakdown, status, created_at)
                        VALUES (?, ?, ?, ?, ?, 'APPROVED', ?)
                        """,
                        (match_id, lost["id"], found["id"], score, json.dumps(breakdown), now)
                    )

                chat_room_id = open_chat_for_confirmed_match(cursor, match_id, lost, found, now)
                created_matches.append({
                    "id": match_id,
                    "lost_item_id": lost["id"],
                    "found_item_id": found["id"],
                    "score": score,
                    "breakdown": breakdown,
                    "status": "APPROVED",
                    "chat_room_id": chat_room_id
                })

    return created_matches

def open_existing_high_confidence_matches() -> int:
    """
    Converts already-pending high-confidence matches into active chat rooms.
    Useful for databases created before automatic chat opening was enabled.
    """
    opened_count = 0
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                m.id as match_id,
                l.*,
                f.id as found_id,
                f.type as found_type,
                f.title as found_title,
                f.category as found_category,
                f.description as found_description,
                f.location as found_location,
                f.item_date as found_item_date,
                f.image_url as found_image_url,
                f.status as found_status,
                f.reporter_id as found_reporter_id,
                f.created_at as found_created_at
            FROM matches m
            JOIN items l ON m.lost_item_id = l.id
            JOIN items f ON m.found_item_id = f.id
            WHERE m.status = 'PENDING'
              AND m.score >= ?
              AND l.status = 'OPEN'
              AND f.status = 'OPEN'
            """,
            (MATCH_CONFIDENCE_THRESHOLD,)
        )
        rows = cursor.fetchall()

        for row in rows:
            data = dict(row)
            lost = {
                "id": data["id"],
                "type": data["type"],
                "title": data["title"],
                "category": data["category"],
                "description": data["description"],
                "location": data["location"],
                "item_date": data["item_date"],
                "image_url": data["image_url"],
                "status": data["status"],
                "reporter_id": data["reporter_id"],
                "created_at": data["created_at"],
            }
            found = {
                "id": data["found_id"],
                "type": data["found_type"],
                "title": data["found_title"],
                "category": data["found_category"],
                "description": data["found_description"],
                "location": data["found_location"],
                "item_date": data["found_item_date"],
                "image_url": data["found_image_url"],
                "status": data["found_status"],
                "reporter_id": data["found_reporter_id"],
                "created_at": data["found_created_at"],
            }
            open_chat_for_confirmed_match(cursor, data["match_id"], lost, found, now)
            opened_count += 1

    return opened_count
