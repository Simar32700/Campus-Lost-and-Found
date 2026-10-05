import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "campus_lost_found.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Security & Authentication
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "campus_lost_found_super_secret_jwt_key_2026_x99a8b7c6d5e4f3")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# College Email Validation Pattern
# Accepts .edu, .ac.in, .ac.uk, .edu.in, or university domain subdomains
COLLEGE_EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@([a-zA-Z0-9-]+\.)*(edu|ac\.[a-zA-Z]+|edu\.[a-zA-Z]+)$"

# Matching Engine Parameters
MATCH_CONFIDENCE_THRESHOLD = 80.0  # >= 80% marks as high-confidence pending match
WEIGHT_CATEGORY = 0.30
WEIGHT_TITLE = 0.35
WEIGHT_DESCRIPTION = 0.20
WEIGHT_LOCATION = 0.15
