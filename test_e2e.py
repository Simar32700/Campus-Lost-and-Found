"""Run the complete prototype journey against an isolated SQLite database.

Usage: python -B test_e2e.py
"""

import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

import database


def authorized(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return authorized(response.json()["access_token"])


def test_full_pipeline():
    with tempfile.TemporaryDirectory() as directory:
        database.DATABASE_PATH = Path(directory) / "test.db"
        from main import app  # Import after selecting the disposable database.

        with TestClient(app) as client:
            assert client.get("/").status_code == 200
            assert "CampusFinder" in client.get("/").text
            assert client.get("/static/css/styles.css").status_code == 200
            assert client.get("/api/health").json() == {"status": "ok"}

            bad = client.post("/api/auth/register", json={
                "email": "intruder@gmail.com", "password": "Password123", "full_name": "Non Student"
            })
            assert bad.status_code == 400

            email = f"test.{uuid.uuid4().hex[:8]}@stanford.edu"
            registered = client.post("/api/auth/register", json={
                "email": email, "password": "Password123", "full_name": "Test Student", "role": "ADMIN"
            })
            assert registered.status_code == 200, registered.text
            assert registered.json()["user"]["role"] == "USER"
            outsider = authorized(registered.json()["access_token"])

            alex = login(client, "alex.chen@campus.edu", "Student@123")
            priya = login(client, "priya.patel@campus.edu", "Student@123")
            admin = login(client, "admin@campus.edu", "Admin@123")

            report = {
                "title": "Unique Green Notebook", "category": "Books",
                "description": "Unique green notebook with a red spine and astronomy notes",
                "location": "North Library Desk", "item_date": "2026-11-24"
            }
            lost = client.post("/api/items/lost", headers=outsider, data=report)
            assert lost.status_code == 200 and lost.json()["status"] == "OPEN"
            assert client.get("/api/items/my-posts", headers=outsider).json()["count"] == 1
            found = client.post("/api/items/found", headers=priya, data=report)
            assert found.status_code == 200 and found.json()["matches_found"] >= 1
            assert client.get(f"/api/items/{found.json()['item_id']}", headers=outsider).status_code == 403
            assert client.get("/api/chat/rooms", headers=outsider).json()["count"] == 0

            assert client.get("/api/items/lost", headers=outsider).status_code == 403
            search = client.get("/api/items/lost?search=MacBook", headers=admin)
            assert search.status_code == 200
            assert any("MacBook" in item["title"] for item in search.json()["items"])
            assert all(item["type"] == "LOST" for item in search.json()["items"])
            assert client.get("/api/items/item-found-001", headers=outsider).status_code == 403

            queue = client.get("/api/admin/matches", headers=admin)
            assert queue.status_code == 200
            match = next(m for m in queue.json()["matches"] if m["lost_id"] == "item-lost-001")
            assert match["score"] >= 80 and match["match_status"] == "PENDING"
            assert match["chat_room_id"] is None
            assert client.get("/api/chat/rooms", headers=alex).json()["count"] == 0
            match_id = match["match_id"]
            assert client.post(f"/api/admin/matches/{match_id}/approve", headers=alex).status_code == 403

            approved = client.post(f"/api/admin/matches/{match_id}/approve", headers=admin)
            assert approved.status_code == 200, approved.text
            room_id = approved.json()["chat_room_id"]
            assert client.post(f"/api/admin/matches/{match_id}/approve", headers=admin).status_code == 400
            assert client.post(f"/api/admin/matches/{match_id}/reject", headers=admin).status_code == 400
            assert any(r["room_id"] == room_id for r in client.get("/api/chat/rooms", headers=alex).json()["rooms"])
            assert any(r["room_id"] == room_id for r in client.get("/api/chat/rooms", headers=priya).json()["rooms"])
            assert client.get(f"/api/chat/rooms/{room_id}/messages", headers=outsider).status_code == 403
            assert client.get("/api/items/item-found-001", headers=alex).status_code == 200

            for headers, message in ((alex, "Can we meet at the library?"), (priya, "Yes, at 3 pm.")):
                sent = client.post(f"/api/chat/rooms/{room_id}/messages", headers=headers, json={"content": message})
                assert sent.status_code == 200, sent.text
            messages = client.get(f"/api/chat/rooms/{room_id}/messages", headers=alex).json()["messages"]
            assert len(messages) >= 3

            first = client.post(f"/api/chat/rooms/{room_id}/resolve", headers=alex)
            assert first.status_code == 200 and first.json()["status"] == "WAITING_FOR_OTHER_USER"
            assert client.get("/api/items/item-lost-001", headers=alex).json()["status"] == "MATCHED"
            second = client.post(f"/api/chat/rooms/{room_id}/resolve", headers=priya)
            assert second.status_code == 200 and second.json()["status"] == "RESOLVED"
            assert client.get("/api/items/item-lost-001", headers=alex).json()["status"] == "CLOSED"
            assert client.post(f"/api/chat/rooms/{room_id}/messages", headers=alex, json={"content": "Late message"}).status_code == 400

            stats = client.get("/api/admin/stats", headers=admin).json()
            assert stats["approved_matches"] >= 1 and stats["resolved_items"] >= 2
            print("PASS: startup, registration, reporting, privacy, search, review, chat and two-person resolution.")


if __name__ == "__main__":
    test_full_pipeline()
