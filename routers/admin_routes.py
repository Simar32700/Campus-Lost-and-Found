import json
import uuid
import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
from auth import require_admin
from database import get_db

router = APIRouter(prefix="/api/admin", tags=["Admin Verification & Workflow"])

@router.get("/matches")
def get_match_suggestions(
    status_filter: Optional[str] = Query("PENDING", description="Filter by status ('PENDING', 'APPROVED', 'REJECTED', 'ALL')"),
    admin_user: dict = Depends(require_admin)
):
    """
    Admin Review Queue. Displays suggested matches side-by-side with
    lost item details, found item details, confidence score, and algorithmic breakdown.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT 
                m.id as match_id,
                m.score,
                m.breakdown,
                m.status as match_status,
                m.reviewed_at,
                m.created_at as match_created_at,
                
                -- Lost Item Details
                l.id as lost_id,
                l.title as lost_title,
                l.category as lost_category,
                l.description as lost_description,
                l.location as lost_location,
                l.item_date as lost_date,
                l.image_url as lost_image,
                l.status as lost_status,
                u_lost.full_name as lost_reporter_name,
                u_lost.email as lost_reporter_email,

                -- Found Item Details
                f.id as found_id,
                f.title as found_title,
                f.category as found_category,
                f.description as found_description,
                f.location as found_location,
                f.item_date as found_date,
                f.image_url as found_image,
                f.status as found_status,
                u_found.full_name as found_reporter_name,
                u_found.email as found_reporter_email,

                -- Associated Chat Room
                cr.id as chat_room_id

            FROM matches m
            JOIN items l ON m.lost_item_id = l.id
            JOIN items f ON m.found_item_id = f.id
            JOIN users u_lost ON l.reporter_id = u_lost.id
            JOIN users u_found ON f.reporter_id = u_found.id
            LEFT JOIN chat_rooms cr ON cr.match_id = m.id
        """
        params = []
        if status_filter and status_filter.upper() != "ALL":
            query += " WHERE m.status = ?"
            params.append(status_filter.upper())

        query += " ORDER BY m.score DESC, m.created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        results = []
        for r in rows:
            d = dict(r)
            try:
                d["breakdown"] = json.loads(d["breakdown"]) if d.get("breakdown") else {}
            except Exception:
                d["breakdown"] = {}
            results.append(d)

        return {"matches": results, "count": len(results)}

@router.post("/matches/{match_id}/approve")
def approve_match(match_id: str, admin_user: dict = Depends(require_admin)):
    """
    Approve match decision:
    1. Sets match status to APPROVED.
    2. Transitions both items to MATCHED status.
    3. Auto-generates a private Chat Room between lost item owner and finder.
    4. Posts an initial system handshake message.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
        match = cursor.fetchone()
        if not match:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
        
        if match["status"] == "APPROVED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Match is already approved")

        lost_item_id = match["lost_item_id"]
        found_item_id = match["found_item_id"]

        # Fetch reporters
        cursor.execute("SELECT reporter_id, title FROM items WHERE id = ?", (lost_item_id,))
        lost_item = cursor.fetchone()
        cursor.execute("SELECT reporter_id, title FROM items WHERE id = ?", (found_item_id,))
        found_item = cursor.fetchone()

        if not lost_item or not found_item:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Associated items no longer exist")

        lost_reporter_id = lost_item["reporter_id"]
        found_reporter_id = found_item["reporter_id"]

        # 1. Update match record
        cursor.execute(
            "UPDATE matches SET status = 'APPROVED', admin_id = ?, reviewed_at = ? WHERE id = ?",
            (admin_user["id"], now, match_id)
        )

        # 2. Update items status to MATCHED
        cursor.execute("UPDATE items SET status = 'MATCHED' WHERE id IN (?, ?)", (lost_item_id, found_item_id))

        # 3. Create or fetch chat room
        cursor.execute("SELECT id FROM chat_rooms WHERE match_id = ?", (match_id,))
        existing_chat = cursor.fetchone()
        if existing_chat:
            chat_room_id = existing_chat["id"]
        else:
            chat_room_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO chat_rooms (id, match_id, lost_reporter_id, found_reporter_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_room_id, match_id, lost_reporter_id, found_reporter_id, now)
            )

            # Insert initial automated system message
            msg_id = str(uuid.uuid4())
            initial_msg = (
                f"🎉 Match Approved! Admin verified that lost item '{lost_item['title']}' "
                f"matches found item '{found_item['title']}'. You may now safely discuss return/handover details."
            )
            cursor.execute(
                """
                INSERT INTO messages (id, chat_room_id, sender_id, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (msg_id, chat_room_id, admin_user["id"], initial_msg, now)
            )

        return {
            "message": "Match approved successfully. Item statuses updated to MATCHED and private chat opened.",
            "match_id": match_id,
            "chat_room_id": chat_room_id
        }

@router.post("/matches/{match_id}/reject")
def reject_match(match_id: str, admin_user: dict = Depends(require_admin)):
    """
    Reject match decision:
    Marks the match as REJECTED. Items remain OPEN to match with other reports.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
        match = cursor.fetchone()
        if not match:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

        cursor.execute(
            "UPDATE matches SET status = 'REJECTED', admin_id = ?, reviewed_at = ? WHERE id = ?",
            (admin_user["id"], now, match_id)
        )

        return {"message": "Match rejected. Items remain open for future candidates.", "match_id": match_id}

@router.get("/stats")
def get_stats(admin_user: dict = Depends(require_admin)):
    """
    Returns administrative key metrics: items reported, pending reviews, active chats.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM items WHERE type = 'LOST'")
        total_lost = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM items WHERE type = 'FOUND'")
        total_found = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM matches WHERE status = 'PENDING'")
        pending_matches = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM matches WHERE status = 'APPROVED'")
        approved_matches = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM items WHERE status = 'CLOSED'")
        resolved_items = cursor.fetchone()["cnt"]

        return {
            "total_lost": total_lost,
            "total_found": total_found,
            "pending_matches": pending_matches,
            "approved_matches": approved_matches,
            "resolved_items": resolved_items
        }

@router.get("/all-items")
def get_all_items(
    type_filter: Optional[str] = Query(None, description="Filter by 'LOST' or 'FOUND'"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    admin_user: dict = Depends(require_admin)
):
    """
    Administrative overview of all items across campus (including confidential found items).
    """
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT i.*, u.full_name as reporter_name, u.email as reporter_email
            FROM items i
            JOIN users u ON i.reporter_id = u.id
            WHERE 1=1
        """
        params = []
        if type_filter:
            query += " AND i.type = ?"
            params.append(type_filter.upper())
        if status_filter and status_filter.upper() != "ALL":
            query += " AND i.status = ?"
            params.append(status_filter.upper())

        query += " ORDER BY i.created_at DESC"
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        return {"items": rows, "count": len(rows)}
