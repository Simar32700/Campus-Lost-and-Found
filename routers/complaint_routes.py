import datetime
import uuid
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from auth import get_current_user, require_admin
from database import get_db
from routers.chat_routes import get_authorized_room

router = APIRouter(prefix="/api/complaints", tags=["Complaints"])

class ComplaintCreate(BaseModel):
    room_id: str
    category: Literal["FALSE_CLAIM", "HARASSMENT", "NO_RESPONSE", "HANDOVER_ISSUE", "OTHER"]
    details: str = Field(min_length=10, max_length=3000)

class ComplaintReview(BaseModel):
    status: Literal["PENDING", "IN_REVIEW", "RESOLVED", "REJECTED"]
    admin_notes: str = Field(min_length=1, max_length=3000)

SELECT = """
    SELECT c.*, reporter.full_name AS reporter_name,
        reported.full_name AS reported_user_name, cr.status AS room_status,
        l.title AS lost_title, f.title AS found_title
    FROM complaints c
    JOIN users reporter ON reporter.id = c.reporter_id
    LEFT JOIN users reported ON reported.id = c.reported_user_id
    JOIN chat_rooms cr ON cr.id = c.room_id
    JOIN matches m ON m.id = cr.match_id
    JOIN items l ON l.id = m.lost_item_id
    JOIN items f ON f.id = m.found_item_id
"""

@router.get("")
def list_complaints(current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        query, params = SELECT, []
        if current_user.get("role") != "ADMIN":
            query += " WHERE c.reporter_id = ?"
            params.append(current_user["id"])
        rows = [dict(row) for row in conn.execute(query + " ORDER BY c.updated_at DESC, c.id", params)]
        counts = {status: sum(row["status"] == status for row in rows)
                  for status in ("PENDING", "IN_REVIEW", "RESOLVED", "REJECTED")}
        counts["ALL"] = len(rows)
        return {"complaints": rows, "counts": counts}

@router.post("")
def submit_complaint(req: ComplaintCreate, current_user: dict = Depends(get_current_user)):
    details = req.details.strip()
    if len(details) < 10:
        raise HTTPException(422, "Please provide at least 10 characters of complaint details")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        room = get_authorized_room(cursor, req.room_id, current_user)
        if current_user["id"] not in (room["lost_reporter_id"], room["found_reporter_id"]):
            raise HTTPException(403, "Only participants can file a complaint")
        dismissed_before = cursor.execute("SELECT 1 FROM complaints WHERE room_id = ?", (req.room_id,)).fetchone()
        if room["status"] != "DISMISSED" and not dismissed_before:
            raise HTTPException(400, "Complaints are available after a chat has been dismissed")
        reported_id = room["found_reporter_id"] if current_user["id"] == room["lost_reporter_id"] else room["lost_reporter_id"]
        if reported_id == current_user["id"]:
            raise HTTPException(400, "You cannot complain against yourself")
        complaint_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO complaints (id, room_id, reporter_id, reported_user_id, source, category, details, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'USER', ?, ?, ?, ?)
            ON CONFLICT(room_id, reporter_id) DO UPDATE SET
                source = 'USER', category = excluded.category, details = excluded.details,
                status = 'PENDING', updated_at = excluded.updated_at
        """, (complaint_id, req.room_id, current_user["id"], reported_id, req.category, details, now, now))
        row = cursor.execute("SELECT id FROM complaints WHERE room_id = ? AND reporter_id = ?", (req.room_id, current_user["id"])).fetchone()
        return {"id": row["id"], "message": "Complaint sent to the admin. You can track it in My Complaints."}

@router.get("/{complaint_id}/conversation")
def complaint_conversation(complaint_id: str, admin: dict = Depends(require_admin)):
    with get_db() as conn:
        complaint = conn.execute(SELECT + " WHERE c.id = ?", (complaint_id,)).fetchone()
        if not complaint:
            raise HTTPException(404, "Complaint not found")
        messages = conn.execute("""
            SELECT m.*, u.full_name AS sender_name FROM messages m
            JOIN users u ON u.id = m.sender_id WHERE m.chat_room_id = ?
            ORDER BY m.created_at, m.id
        """, (complaint["room_id"],)).fetchall()
        return {"complaint": dict(complaint), "messages": [dict(m) for m in messages]}

@router.patch("/{complaint_id}")
def review_complaint(complaint_id: str, req: ComplaintReview, admin: dict = Depends(require_admin)):
    notes = req.admin_notes.strip()
    if not notes:
        raise HTTPException(422, "A review note is required")
    with get_db() as conn:
        result = conn.execute("""
            UPDATE complaints SET status = ?, admin_notes = ?, reviewed_by = ?, updated_at = ? WHERE id = ?
        """, (req.status, notes, admin["id"], datetime.datetime.now(datetime.timezone.utc).isoformat(), complaint_id))
        if result.rowcount != 1:
            raise HTTPException(404, "Complaint not found")
        return {"message": "Complaint review saved"}
