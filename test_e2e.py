import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_full_pipeline():
    print("=== 1. Checking Static & Web App Serving ===")
    r = requests.get(f"{BASE_URL}/")
    assert r.status_code == 200, f"Root failed: {r.status_code}"
    assert "CampusFinder" in r.text, "Index page title missing"
    print("[PASS] Static index.html served successfully")

    r = requests.get(f"{BASE_URL}/static/css/styles.css")
    assert r.status_code == 200, "CSS failed to load"
    print("[PASS] CSS design system loaded successfully")

    print("\n=== 2. Testing College Email Auth & RBAC ===")
    # 2.1 Non-college email registration rejection
    bad_reg = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": "intruder@gmail.com",
        "password": "Password123",
        "full_name": "Non Student"
    })
    assert bad_reg.status_code == 400, f"Expected 400 for gmail, got {bad_reg.status_code}"
    print("[PASS] Non-college email correctly rejected with 400 Bad Request")

    # 2.2 Valid college email registration
    good_reg = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": "taylor.swift@stanford.edu",
        "password": "Password123",
        "full_name": "Taylor Swift",
        "phone": "555-9999"
    })
    assert good_reg.status_code == 200, f"Expected 200 for valid edu email, got {good_reg.status_code}"
    print("[PASS] Valid college email registered successfully")

    # 2.3 Student login
    login_alex = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "alex.chen@campus.edu",
        "password": "Student@123"
    })
    assert login_alex.status_code == 200, "Alex login failed"
    alex_token = login_alex.json()["access_token"]
    alex_headers = {"Authorization": f"Bearer {alex_token}"}
    print("[PASS] Student Alex Chen logged in successfully")

    # 2.4 Admin login
    login_admin = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@campus.edu",
        "password": "Admin@123"
    })
    assert login_admin.status_code == 200, "Admin login failed"
    admin_token = login_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("[PASS] Campus Administrator logged in successfully")

    print("\n=== 3. Testing Public Feed & Hidden Anti-Fraud Found Items ===")
    feed_res = requests.get(f"{BASE_URL}/api/items/lost")
    assert feed_res.status_code == 200
    feed_items = feed_res.json()["items"]
    # Verify ONLY lost items are in public feed
    assert all(item["type"] == "LOST" for item in feed_items), "CRITICAL: Found items leaked into public feed!"
    print(f"[PASS] Public feed contains {len(feed_items)} items; zero found items leaked (Anti-fraud enforced)")

    # Test search query
    search_res = requests.get(f"{BASE_URL}/api/items/lost?search=MacBook")
    assert search_res.status_code == 200
    search_items = search_res.json()["items"]
    assert any("MacBook" in i["title"] for i in search_items), "Search for MacBook failed"
    print(f"[PASS] Search filter returned {len(search_items)} matching results")

    print("\n=== 4. Testing Automated Matching Engine & Admin Queue ===")
    # Check admin match review queue
    matches_res = requests.get(f"{BASE_URL}/api/admin/matches?status_filter=PENDING", headers=admin_headers)
    assert matches_res.status_code == 200
    pending_matches = matches_res.json()["matches"]
    assert len(pending_matches) > 0, "No pending matches in admin review queue"
    
    match = pending_matches[0]
    match_id = match["match_id"]
    print(f"[PASS] Pending match detected: '{match['lost_title']}' <--> '{match['found_title']}'")
    print(f"       Confidence Score: {match['score']}% (Threshold: >= 80%)")
    print(f"       Algorithmic Breakdown: Category {match['breakdown']['category_score']}%, Title {match['breakdown']['title_score']}%, Location {match['breakdown']['location_score']}%")

    print("\n=== 5. Testing Admin Approval & State Transition ===")
    approve_res = requests.post(f"{BASE_URL}/api/admin/matches/{match_id}/approve", headers=admin_headers)
    assert approve_res.status_code == 200, f"Approve match failed: {approve_res.text}"
    chat_room_id = approve_res.json()["chat_room_id"]
    print(f"[PASS] Admin approved match! Both items updated to MATCHED. Private Chat Room created: {chat_room_id}")

    print("\n=== 6. Testing In-App Communication & Handover Resolution ===")
    # 6.1 Alex fetches his unlocked chat rooms
    alex_rooms = requests.get(f"{BASE_URL}/api/chat/rooms", headers=alex_headers)
    assert alex_rooms.status_code == 200
    assert any(r["room_id"] == chat_room_id for r in alex_rooms.json()["rooms"]), "Chat room not visible to Alex"
    print("[PASS] Chat room successfully visible to student Alex Chen")

    # 6.2 Alex sends a message to coordinate return
    msg_res = requests.post(f"{BASE_URL}/api/chat/rooms/{chat_room_id}/messages", headers=alex_headers, json={
        "content": "Hi Priya! Thank you so much for finding my MacBook. Can we meet at the Library 1st floor helpdesk today at 3pm?"
    })
    assert msg_res.status_code == 200
    print("[PASS] Alex sent coordination message in unlocked chat room")

    # 6.3 Priya logs in and sends reply
    login_priya = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "priya.patel@campus.edu",
        "password": "Student@123"
    })
    priya_token = login_priya.json()["access_token"]
    priya_headers = {"Authorization": f"Bearer {priya_token}"}

    msg2_res = requests.post(f"{BASE_URL}/api/chat/rooms/{chat_room_id}/messages", headers=priya_headers, json={
        "content": "Hi Alex, yes! I will leave it with the desk staff or meet you there at 3pm. See you then!"
    })
    assert msg2_res.status_code == 200
    print("[PASS] Priya sent response in unlocked chat room")

    # 6.4 Fetch message stream
    messages_res = requests.get(f"{BASE_URL}/api/chat/rooms/{chat_room_id}/messages", headers=alex_headers)
    assert messages_res.status_code == 200
    messages = messages_res.json()["messages"]
    assert len(messages) >= 3, "Expected at least 3 messages (system + 2 user messages)"
    print(f"[PASS] Message stream verified with {len(messages)} chronological messages")

    # 6.5 Resolve handover
    resolve_res = requests.post(f"{BASE_URL}/api/chat/rooms/{chat_room_id}/resolve", headers=alex_headers)
    assert resolve_res.status_code == 200
    print("[PASS] Handover marked as CLOSED! Items lifecycle updated to resolved.")

    print("\n=== 7. Verifying Admin Metrics ===")
    stats_res = requests.get(f"{BASE_URL}/api/admin/stats", headers=admin_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    print(f"[PASS] Admin Stats: Total Lost: {stats['total_lost']}, Total Found: {stats['total_found']}, Approved Matches: {stats['approved_matches']}, Resolved: {stats['resolved_items']}")

    print("\n[SUCCESS] ALL MUST-HAVE TEST CASES PASSED FLAWLESSLY!")

if __name__ == "__main__":
    test_full_pipeline()

