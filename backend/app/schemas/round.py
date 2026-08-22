from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.round import RoundStatus


class GroupHoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hole_id: UUID
    sequence: int


class GroupMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    participant_id: UUID


class GroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    round_id: UUID
    group_number: int
    members: list[GroupMemberRead]
    holes: list[GroupHoleRead]


class RoundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tournament_id: UUID
    round_number: int
    status: RoundStatus
    created_at: datetime
    updated_at: datetime


class RoundWithGroups(RoundRead):
    groups: list[GroupRead]
