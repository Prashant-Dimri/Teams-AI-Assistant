# app/schemas/auth.py
from pydantic import BaseModel, EmailStr
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str]
    roles: Optional[list]
    full_name: Optional[str]
    email: Optional[str]

class TokenPayload(BaseModel):
    sub: str
