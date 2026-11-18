"""Isolated complaint API checks. Run: python -B test_complaints.py"""
import asyncio
import contextlib
import json
import sqlite3
import sys
sys.dont_write_bytecode = True
import database
import auth
from routers import chat_routes as chat, complaint_routes as complaints
from fastapi import FastAPI

async def run():
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    @contextlib.contextmanager
    def db():
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    for module in (database, auth, chat, complaints):
        module.get_db = db
    database.init_db()
    for uid, role in [('owner','USER'),('finder','USER'),('stranger','USER'),('admin','ADMIN')]:
        conn.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?)', (uid, uid+'@campus.edu','hash',uid,role,None,'2026-10-28'))
    for iid, typ, uid in [('lost','LOST','owner'),('found','FOUND','finder')]:
        conn.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?,?)', (iid,typ,'Wallet','Accessories','Blue wallet','Library','2026-10-28',None,'MATCHED',uid,'2026-10-28'))
    conn.execute("INSERT INTO matches(id,lost_item_id,found_item_id,score,status,created_at) VALUES('match','lost','found',95,'APPROVED','2026-10-28')")
    conn.execute("INSERT INTO chat_rooms(id,match_id,lost_reporter_id,found_reporter_id,created_at) VALUES('room','match','owner','finder','2026-10-28')")
    conn.execute("INSERT INTO messages(id,chat_room_id,sender_id,content,created_at) VALUES('msg','room','finder','Private evidence','2026-10-28')")
    conn.commit()
    app = FastAPI()
    app.include_router(chat.router)
    app.include_router(complaints.router)
    def as_user(uid):
        app.dependency_overrides[auth.get_current_user] = lambda: dict(conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())
    async def request(method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else b''
        events = []
        async def receive():
            return {'type':'http.request','body':body,'more_body':False}
        async def send(event):
            events.append(event)
        await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'','root_path':'','headers':[(b'content-type',b'application/json')],'client':('127.0.0.1',1),'server':('test',80)},receive,send)
        code = next(e['status'] for e in events if e['type']=='http.response.start')
        data = json.loads(b''.join(e.get('body',b'') for e in events if e['type']=='http.response.body'))
        return code, data
    async def submit(details='The other user made a false ownership claim.'):
        return await request('POST','/api/complaints',{'room_id':'room','category':'FALSE_CLAIM','details':details})
    as_user('owner')
    assert (await submit())[0] == 400
    assert (await request('POST','/api/chat/rooms/room/dismiss'))[0] == 200
    assert (await request('POST','/api/chat/rooms/room/dismiss'))[0] == 200
    rows = (await request('GET','/api/complaints'))[1]
    assert rows['counts']['ALL'] == 1
    cid = rows['complaints'][0]['id']
    assert rows['complaints'][0]['source'] == 'AUTOMATIC'
    assert (await submit('          '))[0] == 422
    assert (await submit())[0] == 200
    assert (await request('GET','/api/complaints'))[1]['counts']['ALL'] == 1
    assert (await request('GET',f'/api/complaints/{cid}/conversation'))[0] == 403
    assert (await request('PATCH',f'/api/complaints/{cid}',{'status':'RESOLVED','admin_notes':'Reviewed'}))[0] == 403
    as_user('stranger')
    assert (await request('GET','/api/complaints'))[1]['counts']['ALL'] == 0
    assert (await submit())[0] == 403
    as_user('finder')
    assert (await submit())[0] == 200
    as_user('admin')
    assert (await request('GET','/api/complaints'))[1]['counts']['ALL'] == 2
    code, transcript = await request('GET',f'/api/complaints/{cid}/conversation')
    assert code == 200 and any(m['content']=='Private evidence' for m in transcript['messages'])
    assert (await request('PATCH',f'/api/complaints/{cid}',{'status':'RESOLVED','admin_notes':'Conversation reviewed.'}))[0] == 200
    assert (await request('GET','/api/complaints'))[1]['counts']['RESOLVED'] == 1
    assert (await request('PATCH',f'/api/complaints/{cid}',{'status':'INVALID','admin_notes':'x'}))[0] == 422
    as_user('owner')
    assert (await request('POST','/api/chat/rooms/room/reopen'))[0] == 200
    assert (await request('GET','/api/chat/rooms/room/messages'))[1]['can_complain']
    assert (await request('GET','/api/complaints'))[1]['counts']['ALL'] == 1
    assert (await request('POST','/api/chat/rooms/room/dismiss'))[0] == 200
    assert (await request('GET','/api/complaints'))[1]['counts']['PENDING'] == 1
    conn.execute('DELETE FROM complaints')
    conn.commit()
    database.init_db()
    database.init_db()
    assert conn.execute('SELECT COUNT(*) FROM complaints').fetchone()[0] == 1
    app.dependency_overrides.clear()
    assert (await request('GET','/api/complaints'))[0] == 401
    print('PASS: complaint API, automatic escalation, duplicate prevention, permissions, review, reopen history, validation and legacy migration.')
    conn.close()

if __name__ == '__main__':
    asyncio.run(run())
