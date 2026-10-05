import os
import shutil
import uuid
import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form

from models import MessageCreate
from auth import get_current_user
from config import UPLOAD_DIR
from database import get_db

router = APIRouter(prefix="/api/chat", tags=["In-App Communication"])

ALLOWED_CHAT_MEDIA = {
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".gif": "image",
    ".mp4": "video",
    ".webm": "video",
    ".mov": "video",
}
MAX_CHAT_MEDIA_BYTES = 25 * 1024 * 1024


def get_authorized_room(cursor, room_id: str, current_user: dict):
    cursor.execute("SELECT * FROM chat_rooms WHERE id = ?", (room_id,))
    room = cursor.fetchone()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat room not found")

    is_participant = current_user["id"] in (room["lost_reporter_id"], room["found_reporter_id"])
    is_admin = current_user.get("role") == "ADMIN"
    if not (is_participant or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access this private room")

    return room


def require_open_room(room):
    if room["status"] == "DISMISSED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This chat is dismissed. Reopen the chat before sending messages."
        )
    if room["status"] == "RESOLVED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This case is resolved. Chat is closed."
        )


def insert_system_message(cursor, room_id: str, sender_id: str, content: str, now: str):
    cursor.execute(
        """
        INSERT INTO messages (id, chat_room_id, sender_id, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), room_id, sender_id, content, now)
    )


@router.get("/rooms")
def get_user_chat_rooms(current_user: dict = Depends(get_current_user)):
    """
    Returns all unlocked chat rooms for the logged-in user. Admins can see all rooms.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        is_admin = current_user.get("role") == "ADMIN"

        query = """
            SELECT
                cr.id as room_id,
                cr.match_id,
                cr.created_at as room_created_at,
                cr.status as room_status,
                cr.dismissed_by,
                cr.resolve_lost_confirmed,
                cr.resolve_found_confirmed,
                cr.resolved_at,

                l.id as lost_item_id,
                l.title as lost_item_title,
                l.status as lost_item_status,
                u_lost.id as lost_reporter_id,
                u_lost.full_name as lost_reporter_name,

                f.id as found_item_id,
                f.title as found_item_title,
                f.status as found_item_status,
                u_found.id as found_reporter_id,
                u_found.full_name as found_reporter_name,

                m.score as match_score,

                (
                    SELECT
                        CASE
                            WHEN attachment_type = 'image' THEN '[Photo] ' || content
                            WHEN attachment_type = 'video' THEN '[Video] ' || content
                            ELSE content
                        END
                    FROM messages
                    WHERE chat_room_id = cr.id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) as last_message,
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
    Fetches chronological message log and room state for a match room.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        room = get_authorized_room(cursor, room_id, current_user)

        cursor.execute(
            """
            SELECT
                l.title as lost_title, l.status as lost_status,
                f.title as found_title, f.status as found_status,
                cr.status as room_status,
                cr.dismissed_by,
                cr.resolve_lost_confirmed,
                cr.resolve_found_confirmed,
                cr.resolved_at,
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
            "is_resolved": meta["room_status"] == "RESOLVED",
            "is_dismissed": meta["room_status"] == "DISMISSED",
            "can_send": meta["room_status"] == "OPEN",
            "can_reopen": meta["room_status"] == "DISMISSED" and meta["dismissed_by"] == current_user["id"],
            "my_resolution_confirmed": (
                bool(meta["resolve_lost_confirmed"]) if current_user["id"] == room["lost_reporter_id"]
                else bool(meta["resolve_found_confirmed"]) if current_user["id"] == room["found_reporter_id"]
                else False
            )
        }


@router.post("/rooms/{room_id}/messages")
def send_message(
    room_id: str,
    req: MessageCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Send a text message within an open match room.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        room = get_authorized_room(cursor, room_id, current_user)
        require_open_room(room)

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
            "attachment_url": None,
            "attachment_type": None,
            "attachment_name": None,
            "created_at": now
        }


@router.post("/rooms/{room_id}/messages/media")
async def send_media_message(
    room_id: str,
    file: UploadFile = File(...),
    content: Optional[str] = Form(""),
    current_user: dict = Depends(get_current_user)
):
    """
    Send a photo or video attachment inside an open match room.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    attachment_type = ALLOWED_CHAT_MEDIA.get(ext)
    if not attachment_type:
        allowed = ", ".join(sorted(ALLOWED_CHAT_MEDIA))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid media type. Allowed formats: {allowed}"
        )

    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_CHAT_MEDIA_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat media must be 25MB or smaller")

    with get_db() as conn:
        cursor = conn.cursor()
        room = get_authorized_room(cursor, room_id, current_user)
        require_open_room(room)

        unique_filename = f"chat_{uuid.uuid4().hex}{ext}"
        target_path = UPLOAD_DIR / unique_filename
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        msg_id = str(uuid.uuid4())
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        clean_content = (content or "").strip()
        if not clean_content:
            clean_content = "Photo attached" if attachment_type == "image" else "Video attached"

        cursor.execute(
            """
            INSERT INTO messages (
                id, chat_room_id, sender_id, content,
                attachment_url, attachment_type, attachment_name, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                msg_id,
                room_id,
                current_user["id"],
                clean_content,
                f"/uploads/{unique_filename}",
                attachment_type,
                file.filename,
                now
            )
        )

        return {
            "id": msg_id,
            "chat_room_id": room_id,
            "sender_id": current_user["id"],
            "sender_name": current_user["full_name"],
            "content": clean_content,
            "attachment_url": f"/uploads/{unique_filename}",
            "attachment_type": attachment_type,
            "attachment_name": file.filename,
            "created_at": now
        }


@router.post("/rooms/{room_id}/dismiss")
def dismiss_chat(room_id: str, current_user: dict = Depends(get_current_user)):
    """
    Pauses a suspected false match. Either participant can reopen it later.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        room = get_authorized_room(cursor, room_id, current_user)
        if room["status"] == "RESOLVED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resolved chats cannot be dismissed")

        cursor.execute(
            """
            UPDATE chat_rooms
            SET status = 'DISMISSED',
                dismissed_by = ?,
                dismissed_at = ?,
                resolve_lost_confirmed = 0,
                resolve_found_confirmed = 0
            WHERE id = ?
            """,
            (current_user["id"], now, room_id)
        )
        cursor.execute("SELECT lost_item_id, found_item_id FROM matches WHERE id = ?", (room["match_id"],))
        match_info = cursor.fetchone()
        if match_info:
            cursor.execute(
                "UPDATE items SET status = 'OPEN' WHERE id IN (?, ?) AND status != 'CLOSED'",
                (match_info["lost_item_id"], match_info["found_item_id"])
            )

        insert_system_message(
            cursor,
            room_id,
            current_user["id"],
            f"Chat dismissed by {current_user['full_name']}. Only the user who dismissed it can reopen the chat.",
            now
        )
        return {"message": "Chat dismissed. The match is paused and both reports are open again.", "status": "DISMISSED"}


@router.post("/rooms/{room_id}/reopen")
def reopen_chat(room_id: str, current_user: dict = Depends(get_current_user)):
    """
    Reopens a dismissed chat only for the user who dismissed it.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        room = get_authorized_room(cursor, room_id, current_user)
        if room["status"] == "RESOLVED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resolved chats cannot be reopened")
        if room["status"] != "DISMISSED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only dismissed chats can be reopened")
        if room["dismissed_by"] != current_user["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the user who dismissed this chat can reopen it")

        cursor.execute(
            """
            UPDATE chat_rooms
            SET status = 'OPEN',
                dismissed_by = NULL,
                dismissed_at = NULL
            WHERE id = ?
            """,
            (room_id,)
        )
        cursor.execute("SELECT lost_item_id, found_item_id FROM matches WHERE id = ?", (room["match_id"],))
        match_info = cursor.fetchone()
        if match_info:
            cursor.execute(
                "UPDATE items SET status = 'MATCHED' WHERE id IN (?, ?) AND status != 'CLOSED'",
                (match_info["lost_item_id"], match_info["found_item_id"])
            )

        insert_system_message(cursor, room_id, current_user["id"], f"Chat reopened by {current_user['full_name']}.", now)
        return {"message": "Chat reopened. You can message again.", "status": "OPEN"}


@router.post("/rooms/{room_id}/resolve")
def resolve_handover(room_id: str, current_user: dict = Depends(get_current_user)):
    """
    Records one user's handover confirmation. Both matched users must confirm
    before items are CLOSED and the chat becomes read-only.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        room = get_authorized_room(cursor, room_id, current_user)
        if room["status"] == "DISMISSED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reopen the dismissed chat before resolving it")
        if room["status"] == "RESOLVED":
            return {"message": "This case is already resolved and the chat is closed.", "status": "RESOLVED"}

        if current_user["id"] == room["lost_reporter_id"]:
            if room["resolve_lost_confirmed"]:
                return {"message": "Your resolution confirmation is already saved. Waiting for the other user.", "status": "WAITING_FOR_OTHER_USER"}
            cursor.execute("UPDATE chat_rooms SET resolve_lost_confirmed = 1 WHERE id = ?", (room_id,))
        elif current_user["id"] == room["found_reporter_id"]:
            if room["resolve_found_confirmed"]:
                return {"message": "Your resolution confirmation is already saved. Waiting for the other user.", "status": "WAITING_FOR_OTHER_USER"}
            cursor.execute("UPDATE chat_rooms SET resolve_found_confirmed = 1 WHERE id = ?", (room_id,))
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the lost owner and finder can confirm resolution")

        insert_system_message(
            cursor,
            room_id,
            current_user["id"],
            f"Resolution confirmed by {current_user['full_name']}. Waiting for the other user if they have not confirmed yet.",
            now
        )

        cursor.execute("SELECT * FROM chat_rooms WHERE id = ?", (room_id,))
        updated_room = cursor.fetchone()
        both_confirmed = bool(updated_room["resolve_lost_confirmed"]) and bool(updated_room["resolve_found_confirmed"])

        if both_confirmed:
            cursor.execute("SELECT lost_item_id, found_item_id FROM matches WHERE id = ?", (room["match_id"],))
            match_info = cursor.fetchone()
            if match_info:
                cursor.execute(
                    "UPDATE items SET status = 'CLOSED' WHERE id IN (?, ?)",
                    (match_info["lost_item_id"], match_info["found_item_id"])
                )
            cursor.execute("UPDATE chat_rooms SET status = 'RESOLVED', resolved_at = ? WHERE id = ?", (now, room_id))
            insert_system_message(
                cursor,
                room_id,
                current_user["id"],
                "Both users confirmed the exchange. This case is now resolved and the chat is closed.",
                now
            )
            return {"message": "Both users confirmed. Item handover completed and chat closed.", "status": "RESOLVED"}

        return {"message": "Your resolution confirmation was saved. Waiting for the other user to confirm.", "status": "WAITING_FOR_OTHER_USER"}


@router.post("/rooms/{room_id}/unresolve")
def unresolve_handover(room_id: str, current_user: dict = Depends(get_current_user)):
    """
    Lets a participant remove their own resolution confirmation while the
    other participant has not completed the two-sided resolution yet.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.cursor()
        room = get_authorized_room(cursor, room_id, current_user)
        if room["status"] == "DISMISSED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reopen the dismissed chat before changing resolution")
        if room["status"] == "RESOLVED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Both users already resolved this case. It cannot be changed now")

        if current_user["id"] == room["lost_reporter_id"]:
            if not room["resolve_lost_confirmed"]:
                return {"message": "Your case is already marked not resolved.", "status": "OPEN"}
            cursor.execute("UPDATE chat_rooms SET resolve_lost_confirmed = 0 WHERE id = ?", (room_id,))
        elif current_user["id"] == room["found_reporter_id"]:
            if not room["resolve_found_confirmed"]:
                return {"message": "Your case is already marked not resolved.", "status": "OPEN"}
            cursor.execute("UPDATE chat_rooms SET resolve_found_confirmed = 0 WHERE id = ?", (room_id,))
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the lost owner and finder can change resolution")

        insert_system_message(
            cursor,
            room_id,
            current_user["id"],
            f"Resolution removed by {current_user['full_name']}. The case is still open.",
            now
        )
        return {"message": "Marked as not resolved. Chat remains open.", "status": "OPEN"}
