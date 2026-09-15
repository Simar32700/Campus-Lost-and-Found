import uuid
import datetime
from fastapi import APIRouter, HTTPException, status, Depends
from models import MessageCreate
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/api/chat", tags=["In-App Communication"])

@router.get("/rooms")
def get_user_chat_rooms(current_user: dict = Depends(get_current_user)):
    """
    Returns all unlocked chat rooms for the logged-in user (as owner or finder).
    Admins can see all active rooms.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        is_admin = current_user.get("role") == "ADMIN"
        
        query = """
            SELECT 
                cr.id as room_id,
                cr.match_id,
                cr.created_at as room_created_at,
                
                -- Lost item & reporter
                l.id as lost_item_id,
                l.title as lost_item_title,
                l.status as lost_item_status,
                u_lost.id as lost_reporter_id,
                u_lost.full_name as lost_reporter_name,
                
                -- Found item & reporter
                f.id as found_item_id,
                f.title as found_item_title,
                f.status as found_item_status,
                u_found.id as found_reporter_id,
                u_found.full_name as found_reporter_name,
                
                -- Match info
                m.score as match_score,
                
                -- Latest message
                (SELECT content FROM messages WHERE chat_room_id = cr.id ORDER BY created_at DESC LIMIT 1) as last_message,
                (SELECT created_at FROM messages WHERE chat_room_id = cr.id ORDER BY created_at DESC LIMIT 1) as last_message_time

            FROM chat_rooms cr
            JOIN matches m ON cr.match_id = m.id
            JOIN items l ON m.lost_item_id = l.id
            JOIN items f ON m.found_item_id = f.id
            JOIN users u_lost ON cr.lost_reporter_id = u_lost.id
            JOIN users u_found ON cr.found_reporter_id = u_found.id
        """
        params = []
        if not is_admin:
            query += " WHERE (cr.lost_reporter_id = ? OR cr.found_reporter_id = ?)"
            params.extend([current_user["id"], current_user["id"]])

        query += " ORDER BY cr.created_at DESC"
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]

        # Decorate with counterpart information
        for r in rows:
            if current_user["id"] == r["lost_reporter_id"]:
                r["counterpart_name"] = r["found_reporter_name"]
                r["my_role"] = "Lost Item Owner"
            elif current_user["id"] == r["found_reporter_id"]:
                r["counterpart_name"] = r["lost_reporter_name"]
                r["my_role"] = "Item Finder"
            else:
                r["counterpart_name"] = f"{r['lost_reporter_name']} & {r['found_reporter_name']}"
                r["my_role"] = "Administrator"

        return {"rooms": rows, "count": len(rows)}

@router.get("/rooms/{room_id}/messages")
def get_room_messages(room_id: str, current_user: dict = Depends(get_current_user)):
    """
    Fetches chronological message log for an approved match room.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chat_rooms WHERE id = ?", (room_id,))
        room = cursor.fetchone()
        if not room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found")

        # Authorization check
        is_participant = current_user["id"] in (room["lost_reporter_id"], room["found_reporter_id"])
        is_admin = current_user.get("role") == "ADMIN"
        if not (is_participant or is_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to this private room is forbidden")

        # Fetch room metadata
        cursor.execute(
            """
            SELECT 
                l.title as lost_title, l.status as lost_status,
                f.title as found_title, f.status as found_status,
                u_lost.full_name as lost_reporter_name,
                u_found.full_name as found_reporter_name
            FROM chat_rooms cr
            JOIN matches m ON cr.match_id = m.id
            JOIN items l ON m.lost_item_id = l.id
            JOIN items f ON m.found_item_id = f.id
            JOIN users u_lost ON cr.lost_reporter_id = u_lost.id
            JOIN users u_found ON cr.found_reporter_id = u_found.id
            WHERE cr.id = ?
            """,
            (room_id,)
        )
        meta = dict(cursor.fetchone())

        # Fetch messages
        cursor.execute(
            """
            SELECT m.*, u.full_name as sender_name, u.role as sender_role
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.chat_room_id = ?
            ORDER BY m.created_at ASC
            """,
            (room_id,)
        )
        messages = [dict(m) for m in cursor.fetchall()]

        return {
            "room_id": room_id,
            "meta": meta,
            "messages": messages,
            "is_resolved": meta["lost_status"] == "CLOSED" and meta["found_status"] == "CLOSED"
        }

@router.post("/rooms/{room_id}/messages")
def send_message(
    room_id: str,
    req: MessageCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Send a message within an approved match room.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chat_rooms WHERE id = ?", (room_id,))
        room = cursor.fetchone()
        if not room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found")

        is_participant = current_user["id"] in (room["lost_reporter_id"], room["found_reporter_id"])
        is_admin = current_user.get("role") == "ADMIN"
        if not (is_participant or is_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot message in this room")

        msg_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        cursor.execute(
            """
            INSERT INTO messages (id, chat_room_id, sender_id, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (msg_id, room_id, current_user["id"], req.content.strip(), now)
        )

        return {
            "id": msg_id,
            "chat_room_id": room_id,
            "sender_id": current_user["id"],
            "sender_name": current_user["full_name"],
            "content": req.content.strip(),
            "created_at": now
        }

@router.post("/rooms/{room_id}/resolve")
def resolve_handover(room_id: str, current_user: dict = Depends(get_current_user)):
    """
    Mark both matched items as CLOSED upon successful physical return/handover.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chat_rooms WHERE id = ?", (room_id,))
        room = cursor.fetchone()
        if not room:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found")

        is_participant = current_user["id"] in (room["lost_reporter_id"], room["found_reporter_id"])
        is_admin = current_user.get("role") == "ADMIN"
        if not (is_participant or is_admin):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized")

        # Fetch match and items
        cursor.execute("SELECT lost_item_id, found_item_id FROM matches WHERE id = ?", (room["match_id"],))
        match_info = cursor.fetchone()
        if match_info:
            cursor.execute(
                "UPDATE items SET status = 'CLOSED' WHERE id IN (?, ?)",
                (match_info["lost_item_id"], match_info["found_item_id"])
            )

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        msg_id = str(uuid.uuid4())
        cursor.execute(
            """
            INSERT INTO messages (id, chat_room_id, sender_id, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                msg_id,
                room_id,
                current_user["id"],
                f"✅ Handover resolved! Marked as CLOSED by {current_user['full_name']}. Thank you for using Campus Lost & Found.",
                now
            )
        )

        return {"message": "Item handover completed and marked as CLOSED"}
