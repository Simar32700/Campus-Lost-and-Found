from typing import Optional
from pydantic import BaseModel, Field

class UserRegister(BaseModel):
    email: str
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=2)
    phone: Optional[str] = None
    role: Optional[str] = "USER"

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    phone: Optional[str] = None
    created_at: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class ItemCreate(BaseModel):
    type: str  # 'LOST' or 'FOUND'
    title: str = Field(min_length=2, max_length=150)
    category: str
    description: str = Field(min_length=3)
    location: str = Field(min_length=2)
    item_date: str
    image_url: Optional[str] = None

class ItemUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    item_date: Optional[str] = None
    image_url: Optional[str] = None
    status: Optional[str] = None  # 'OPEN', 'MATCHED', 'CLOSED'

class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

class MatchDecision(BaseModel):
    status: str  # 'APPROVED' or 'REJECTED'
