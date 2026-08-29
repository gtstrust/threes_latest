from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PlayerCreate(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str | None = None


class PlayerUpdate(BaseModel):
    display_name: str | None = None


class ProvisionProfile(BaseModel):
    """Optional body for POST /players.

    Carries the referral code the new player arrived with, if any. Optional
    because the overwhelming majority of logins have no code and the endpoint
    predates this one — an empty body must keep working.
    """

    referral_code: str | None = Field(default=None, max_length=16)


class PlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    display_name: str | None
    created_at: datetime
    updated_at: datetime


class ReferralsRead(BaseModel):
    """A player's own referral code and what it has brought in.

    Attribution only — there is nothing to claim here. The count exists to answer
    "is word of mouth working?", which is worth being able to ask before there is
    any revenue to fund a reward for it.
    """

    referral_code: str
    players_referred: int
