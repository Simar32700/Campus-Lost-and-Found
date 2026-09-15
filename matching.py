import re
import json
import uuid
import datetime
from difflib import SequenceMatcher
from config import (
    MATCH_CONFIDENCE_THRESHOLD,
    WEIGHT_CATEGORY,
    WEIGHT_TITLE,
    WEIGHT_DESCRIPTION,
    WEIGHT_LOCATION
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

def clean_and_tokenize(text: str) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
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

def calculate_match_score(lost_item: dict, found_item: dict) -> tuple[float, dict]:
    """
    Computes percentage confidence score (0 - 100) between a lost item and a found item.
    Returns (total_score, breakdown_dict).
    """
    # 1. Category similarity (Weight: 30%)
    cat_lost = (lost_item.get("category") or "").strip().lower()
    cat_found = (found_item.get("category") or "").strip().lower()
    if cat_lost == cat_found:
        score_cat = 1.0
    elif cat_lost in cat_found or cat_found in cat_lost:
        score_cat = 0.6
    else:
        score_cat = 0.0

    # 2. Title similarity (Weight: 35%)
    title_lost = lost_item.get("title") or ""
    title_found = found_item.get("title") or ""
    score_title = calculate_text_similarity(title_lost, title_found)

    # 3. Description similarity (Weight: 20%)
    desc_lost = lost_item.get("description") or ""
    desc_found = found_item.get("description") or ""
    tokens_desc1 = clean_and_tokenize(desc_lost)
    tokens_desc2 = clean_and_tokenize(desc_found)
    score_desc = calculate_jaccard(tokens_desc1, tokens_desc2)

    # 4. Location proximity (Weight: 15%)
    loc_lost = (lost_item.get("location") or "").lower()
    loc_found = (found_item.get("location") or "").lower()
    tokens_loc1 = clean_and_tokenize(loc_lost)
    tokens_loc2 = clean_and_tokenize(loc_found)
    
    if tokens_loc1 and tokens_loc2 and tokens_loc1.intersection(tokens_loc2):
        score_loc = calculate_jaccard(tokens_loc1, tokens_loc2)
        # Boost if strong keyword match like "library", "cafeteria", "gym"
        if any(term in loc_lost and term in loc_found for term in ["library", "gym", "hall", "cafeteria", "canteen", "lab", "quad", "dorm", "hostel", "building"]):
            score_loc = max(score_loc, 0.85)
    else:
        score_loc = 0.0

    # Weighted calculation
    total_score = (
        (WEIGHT_CATEGORY * score_cat) +
        (WEIGHT_TITLE * score_title) +
        (WEIGHT_DESCRIPTION * score_desc) +
        (WEIGHT_LOCATION * score_loc)
    ) * 100.0

    total_score = round(min(100.0, max(0.0, total_score)), 1)

    breakdown = {
        "category_score": round(score_cat * 100, 1),
        "title_score": round(score_title * 100, 1),
        "description_score": round(score_desc * 100, 1),
        "location_score": round(score_loc * 100, 1),
        "threshold": MATCH_CONFIDENCE_THRESHOLD,
        "is_match": total_score >= MATCH_CONFIDENCE_THRESHOLD
    }

    return total_score, breakdown

def evaluate_item_matches(item_id: str) -> list[dict]:
    """
    Evaluates an item against candidate items of the opposite type.
    Creates pending match suggestions for scores >= MATCH_CONFIDENCE_THRESHOLD (80%).
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
                if not existing:
                    match_id = str(uuid.uuid4())
                    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    cursor.execute(
                        """
                        INSERT INTO matches (id, lost_item_id, found_item_id, score, breakdown, status, created_at)
                        VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
                        """,
                        (match_id, lost["id"], found["id"], score, json.dumps(breakdown), now)
                    )
                    created_matches.append({
                        "id": match_id,
                        "lost_item_id": lost["id"],
                        "found_item_id": found["id"],
                        "score": score,
                        "breakdown": breakdown,
                        "status": "PENDING"
                    })

    return created_matches
