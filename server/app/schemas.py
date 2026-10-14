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
class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    full_name: str | None
    state: str | None
    zip: str | None
    bio: str | None
    interests: str | None
    site: str | None
    avatar_ref: str | None
class MeResponse(AccountResponse):
    profile: ProfileResponse
class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=40)
    zip: str | None = Field(default=None, max_length=20)
    bio: str | None = Field(default=None, max_length=2000)
    interests: str | None = Field(default=None, max_length=4000)
    site: str | None = Field(default=None, max_length=255)
    avatar_ref: str | None = Field(default=None, max_length=255)
