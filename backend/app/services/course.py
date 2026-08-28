"""Course and hole business logic.

Courses are shared reference data rather than tournament-owned, so the rules here
are mostly about keeping one club from becoming several records.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.models.course import Course, Hole
from app.repositories.course import CourseRepository
from app.repositories.player import PlayerRepository
from app.schemas.course import CourseCreate, CourseUpdate, HoleUpsert


class CourseError(Exception):
    """Base for course domain errors. Routers map these onto status codes."""


class CreatorProfileMissing(CourseError):
    """The caller holds a valid JWT but has no `players` row yet."""


class DuplicateCourseName(CourseError):
    """A course with this name already exists, ignoring case."""

    def __init__(self, name: str, existing_id: UUID) -> None:
        self.name = name
        self.existing_id = existing_id
        super().__init__(
            f"A course named {name!r} already exists (id {existing_id}). "
            "Course names are compared without case, so reuse that one."
        )


class CourseService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = CourseRepository(session)
        self._players = PlayerRepository(session)

    async def create(self, creator: CurrentUser, payload: CourseCreate) -> Course:
        """Create a course.

        Raises:
            CreatorProfileMissing: If the caller hasn't provisioned a profile.
            DuplicateCourseName: If the name is taken, ignoring case. Checked
                here so the caller gets the existing course's id back rather
                than a bare integrity error.
        """
        if await self._players.get_by_id(creator.id) is None:
            raise CreatorProfileMissing

        existing = await self._repository.get_by_name(payload.name)
        if existing is not None:
            raise DuplicateCourseName(payload.name, existing.id)

        return await self._repository.create(creator.id, payload)

    async def get_by_id(self, course_id: UUID) -> Course | None:
        return await self._repository.get_by_id(course_id)

    async def get_with_holes(self, course_id: UUID) -> Course | None:
        return await self._repository.get_with_holes(course_id)

    async def search(self, name: str | None = None) -> Sequence[tuple[Course, int]]:
        """Courses with their hole counts, so an unplayable one is visible as such."""
        return await self._repository.search(name)

    async def update(self, course: Course, updates: CourseUpdate) -> Course:
        """Rename or relocate a course.

        Raises:
            DuplicateCourseName: If the new name collides with another course.
        """
        if updates.name is not None:
            clash = await self._repository.get_by_name(updates.name)
            if clash is not None and clash.id != course.id:
                raise DuplicateCourseName(updates.name, clash.id)
        return await self._repository.update(course, updates)

    async def list_holes(self, course_id: UUID) -> Sequence[Hole]:
        return await self._repository.list_holes(course_id)

    async def upsert_holes(self, course_id: UUID, holes: Sequence[HoleUpsert]) -> Sequence[Hole]:
        return await self._repository.upsert_holes(course_id, holes)

    async def holes_belong_to_course(self, course_id: UUID, hole_ids: Sequence[UUID]) -> bool:
        return await self._repository.holes_belong_to_course(course_id, hole_ids)
