from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class PlayerCreate(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str | None = None


class PlayerUpdate(BaseModel):
    display_name: str | None = None


class PlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str | None
    created_at: datetime
    updated_at: datetime
