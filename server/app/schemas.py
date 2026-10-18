from typing import Literal
from pydantic import AnyHttpUrl, model_validator
from datetime import datetime
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
    identifier: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    password: str = Field(min_length=1, max_length=128)
    @model_validator(mode="after")
    def require_identifier(self):
        if not self.identifier and not self.email:
            raise ValueError("Enter an email address or username")
        return self
class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)
class RevokeRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)
class RecoveryEmailRequest(BaseModel):
    email: EmailStr
class PasswordResetComplete(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{8}$")
    password: str = Field(min_length=12, max_length=128)
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
class FavoriteCreate(BaseModel):
    category: str = Field(min_length=1, max_length=60)
    provider_id: str = Field(min_length=1, max_length=120)
class FavoriteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category: str
    provider_id: str
    created_at: datetime
class SubmissionCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=60)
    venue: str = Field(min_length=1, max_length=255)
    public_link: AnyHttpUrl | None = None
    event_date_start: datetime
    event_date_end: datetime | None = None
    @model_validator(mode="after")
    def validate_event_dates(self):
        if self.event_date_start.utcoffset() is None:
            raise ValueError("Start date must include a timezone")
        if self.event_date_end is not None:
            if self.event_date_end.utcoffset() is None:
                raise ValueError("End date must include a timezone")
            if self.event_date_end < self.event_date_start:
                raise ValueError("End date must be after the start date")
        return self
class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    event_type: str
    venue: str
    public_link: str | None
    event_date_start: datetime
    event_date_end: datetime | None
    submitted_at: datetime
    status: str
class ModerationRequest(BaseModel):
    action: Literal["approve", "reject"]
    reason: str | None = Field(default=None, max_length=1000)
class CommunityPostCreate(BaseModel):
    category: Literal["general", "events", "music", "movies_tv", "games", "sports", "festivals"]
    title: str = Field(min_length=4, max_length=160)
    body: str = Field(min_length=1, max_length=10000)
class CommunityReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
class CommunityReportCreate(BaseModel):
    target_type: Literal["post", "reply"]
    target_id: str = Field(min_length=36, max_length=36)
    reason: str = Field(min_length=5, max_length=1000)
class CommunityModerationRequest(BaseModel):
    action: Literal["dismiss", "hide"]
    reason: str | None = Field(default=None, max_length=1000)
