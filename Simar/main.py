import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from config import BASE_DIR, UPLOAD_DIR
from database import init_db
from seed_data import seed_initial_data
from matching import open_existing_high_confidence_matches
from routers.auth_routes import router as auth_router
from routers.item_routes import router as item_router
from routers.admin_routes import router as admin_router
from routers.chat_routes import router as chat_router

# Initialize database schema & seed initial data
init_db()
seed_initial_data()
open_existing_high_confidence_matches()

app = FastAPI(
    title="Campus Lost & Found Platform",
    description="Automated AI match scoring, fraud-proof item cataloging, admin verification queue, and in-app coordination.",
    version="1.0.0"
)

# Enable CORS for local cross-origin development if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(auth_router)
app.include_router(item_router)
app.include_router(admin_router)
app.include_router(chat_router)

# Mount Uploads directory for photo attachments
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Mount Static assets directory (CSS, JS, images)
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", include_in_schema=False)
async def serve_index():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Campus Lost & Found API is running. Access interactive documentation at /docs"}

if __name__ == "__main__":
    import uvicorn
    print("[INFO] Starting Campus Lost & Found Prototype server on http://127.0.0.1:8000 ...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
