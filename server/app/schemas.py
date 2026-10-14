from pydantic import BaseModel, ConfigDict, EmailStr, Field
class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(
        min_length=3,
        max_length=40,
        pattern=r"^[A-Za-z0-9_]+$",
    )
    password: str = Field(min_length=12, max_length=128)
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)
class RevokeRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: EmailStr
    username: str
    role: str
