import os
import uuid
import datetime
import shutil
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form, Query
from config import UPLOAD_DIR
from database import get_db
from auth import get_current_user, get_optional_current_user
from matching import evaluate_item_matches

router = APIRouter(prefix="/api/items", tags=["Items"])

@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Accepts an uploaded image file, verifies extension, saves it locally,
    and returns its accessible URL path.
    """
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed formats: {', '.join(allowed_extensions)}"
        )
    
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    target_path = UPLOAD_DIR / unique_filename

    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"image_url": f"/uploads/{unique_filename}"}

@router.get("/lost")
def list_lost_items(
    search: Optional[str] = Query(None, description="Search keyword across title/description/location"),
    category: Optional[str] = Query(None, description="Filter by item category"),
    location: Optional[str] = Query(None, description="Filter by location keyword"),
    status_filter: Optional[str] = Query("OPEN", description="Filter by status ('OPEN', 'MATCHED', 'CLOSED', 'ALL')"),
    current_user: Optional[dict] = Depends(get_optional_current_user)
):
    """
    Public Lost Items Catalog. Only items with type 'LOST' are returned.
    Supports real-time search and multi-criteria filtering.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT i.*, u.full_name as reporter_name, u.email as reporter_email
            FROM items i
            JOIN users u ON i.reporter_id = u.id
            WHERE i.type = 'LOST'
        """
        params = []

        if status_filter and status_filter.upper() != "ALL":
            query += " AND i.status = ?"
            params.append(status_filter.upper())

        if category and category.lower() != "all":
            query += " AND LOWER(i.category) = LOWER(?)"
            params.append(category)

        if location and location.strip():
            query += " AND LOWER(i.location) LIKE ?"
            params.append(f"%{location.strip().lower()}%")

        if search and search.strip():
            s = f"%{search.strip().lower()}%"
            query += " AND (LOWER(i.title) LIKE ? OR LOWER(i.description) LIKE ? OR LOWER(i.location) LIKE ?)"
            params.extend([s, s, s])

        query += " ORDER BY i.created_at DESC"
        cursor.execute(query, params)
        rows = [dict(row) for row in cursor.fetchall()]
        return {"items": rows, "count": len(rows)}

@router.post("/lost")
def report_lost_item(
    title: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    location: str = Form(...),
    item_date: str = Form(...),
    image: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Report a Lost Item. Published to the public campus lost feed and
    automatically evaluated by the matching engine against all open found items.
    """
    final_image_url = image_url
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            unique_name = f"{uuid.uuid4().hex}{ext}"
            with open(UPLOAD_DIR / unique_name, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)
            final_image_url = f"/uploads/{unique_name}"

    item_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO items (id, type, title, category, description, location, item_date, image_url, status, reporter_id, created_at)
            VALUES (?, 'LOST', ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            """,
            (item_id, title.strip(), category.strip(), description.strip(), location.strip(), item_date.strip(), final_image_url, current_user["id"], now)
        )

    # Run matching engine asynchronously / immediately
    matches = evaluate_item_matches(item_id)

    return {
        "message": "Lost item reported successfully",
        "item_id": item_id,
        "matches_found": len(matches),
        "status": "OPEN"
    }

@router.post("/found")
def report_found_item(
    title: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    location: str = Form(...),
    item_date: str = Form(...),
    image: Optional[UploadFile] = File(None),
    image_url: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Report a Found Item.
    SECURITY / ANTI-FRAUD REQUIREMENT: Stored hidden from public feeds to prevent
    fraudulent claims. Evaluated by matching engine and reviewed by administrators.
    """
    final_image_url = image_url
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            unique_name = f"{uuid.uuid4().hex}{ext}"
            with open(UPLOAD_DIR / unique_name, "wb") as buffer:
                shutil.copyfileobj(image.file, buffer)
            final_image_url = f"/uploads/{unique_name}"

    item_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO items (id, type, title, category, description, location, item_date, image_url, status, reporter_id, created_at)
            VALUES (?, 'FOUND', ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
            """,
            (item_id, title.strip(), category.strip(), description.strip(), location.strip(), item_date.strip(), final_image_url, current_user["id"], now)
        )

    # Run matching engine against open lost items
    matches = evaluate_item_matches(item_id)

    return {
        "message": "Found item reported securely. Details are protected from fraudulent public browsing and have been queued for administrative matching.",
        "item_id": item_id,
        "matches_found": len(matches),
        "status": "OPEN"
    }

@router.get("/my-posts")
def get_my_posts(current_user: dict = Depends(get_current_user)):
    """
    Returns all items reported by current user (both Lost and Found),
    along with lifecycle status and any active chat room link.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT i.*,
                   m.id as match_id,
                   m.status as match_status,
                   cr.id as chat_room_id
            FROM items i
            LEFT JOIN matches m ON (i.id = m.lost_item_id OR i.id = m.found_item_id) AND m.status = 'APPROVED'
            LEFT JOIN chat_rooms cr ON cr.match_id = m.id
            WHERE i.reporter_id = ?
            ORDER BY i.created_at DESC
            """,
            (current_user["id"],)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        return {"items": rows, "count": len(rows)}

@router.get("/{item_id}")
def get_item_details(item_id: str, current_user: dict = Depends(get_current_user)):
    """
    Fetch details for an item. Found items are restricted to:
    - Reporter
    - Administrator
    - Legitimate matched claimant once approved
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT i.*, u.full_name as reporter_name, u.email as reporter_email
            FROM items i
            JOIN users u ON i.reporter_id = u.id
            WHERE i.id = ?
            """,
            (item_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

        item = dict(row)

        if item["type"] == "FOUND":
            is_reporter = item["reporter_id"] == current_user["id"]
            is_admin = current_user.get("role") == "ADMIN"
            
            # Check if current user is approved matched owner
            cursor.execute(
                """
                SELECT m.id FROM matches m
                JOIN items lost ON m.lost_item_id = lost.id
                WHERE m.found_item_id = ? AND m.status = 'APPROVED' AND lost.reporter_id = ?
                """,
                (item_id, current_user["id"])
            )
            is_matched_claimant = bool(cursor.fetchone())

            if not (is_reporter or is_admin or is_matched_claimant):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Found item details are confidential and accessible only to admins, the finder, or verified claimants."
                )

        return item

@router.put("/{item_id}")
def update_item(
    item_id: str,
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    item_date: Optional[str] = Form(None),
    status_val: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

        item = dict(row)
        if item["reporter_id"] != current_user["id"] and current_user.get("role") != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to edit this item")

        new_title = title if title is not None else item["title"]
        new_category = category if category is not None else item["category"]
        new_description = description if description is not None else item["description"]
        new_location = location if location is not None else item["location"]
        new_date = item_date if item_date is not None else item["item_date"]
        new_status = status_val.upper() if status_val is not None else item["status"]

        cursor.execute(
            """
            UPDATE items
            SET title = ?, category = ?, description = ?, location = ?, item_date = ?, status = ?
            WHERE id = ?
            """,
            (new_title, new_category, new_description, new_location, new_date, new_status, item_id)
        )

        # If updated and open, re-evaluate matching
        if new_status == "OPEN":
            evaluate_item_matches(item_id)

        return {"message": "Item updated successfully"}

@router.delete("/{item_id}")
def delete_item(item_id: str, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

        item = dict(row)
        if item["reporter_id"] != current_user["id"] and current_user.get("role") != "ADMIN":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this item")

        cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))
        return {"message": "Item deleted successfully"}
