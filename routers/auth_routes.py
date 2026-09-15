import uuid
import datetime
from fastapi import APIRouter, HTTPException, status, Depends
from models import UserRegister, UserLogin, TokenResponse, UserResponse
from auth import (
    hash_password,
    verify_password,
    is_valid_college_email,
    create_access_token,
    get_current_user
)
from database import get_db

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register", response_model=TokenResponse)
def register(req: UserRegister):
    email = req.email.strip().lower()
    
    # Enforce college email domain rule
    if not is_valid_college_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration requires a valid college email address (e.g. your_name@college.edu or .ac.* domain)"
        )
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this college email already exists"
            )
        
        user_id = str(uuid.uuid4())
        pwd_hash = hash_password(req.password)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Determine role: if explicit ADMIN or contains admin@, allow for prototype testing, else USER
        role = "ADMIN" if req.role == "ADMIN" or email.startswith("admin@") else "USER"
        
        cursor.execute(
            """
            INSERT INTO users (id, email, password_hash, full_name, role, phone, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, email, pwd_hash, req.full_name.strip(), role, req.phone, now)
        )
        
        token = create_access_token({"sub": user_id, "role": role, "email": email})
        
        user_resp = UserResponse(
            id=user_id,
            email=email,
            full_name=req.full_name.strip(),
            role=role,
            phone=req.phone,
            created_at=now
        )
        return TokenResponse(access_token=token, user=user_resp)

@router.post("/login", response_model=TokenResponse)
def login(req: UserLogin):
    email = req.email.strip().lower()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if not row or not verify_password(req.password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid college email or password"
            )
        
        user = dict(row)
        token = create_access_token({"sub": user["id"], "role": user["role"], "email": user["email"]})
        
        user_resp = UserResponse(
            id=user["id"],
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"],
            phone=user["phone"],
            created_at=user["created_at"]
        )
        return TokenResponse(access_token=token, user=user_resp)

@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        full_name=current_user["full_name"],
        role=current_user["role"],
        phone=current_user.get("phone"),
        created_at=current_user["created_at"]
    )
