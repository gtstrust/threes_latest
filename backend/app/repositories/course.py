from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.course import Course, Hole
from app.schemas.course import CourseCreate, CourseUpdate, HoleUpsert


class CourseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, course_id: UUID) -> Course | None:
        return await self._session.get(Course, course_id)

    async def get_with_holes(self, course_id: UUID) -> Course | None:
        result = await self._session.execute(
            select(Course).where(Course.id == course_id).options(selectinload(Course.holes))
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Course | None:
        """Case-insensitive lookup, matching the unique index on lower(name)."""
        result = await self._session.execute(
            select(Course).where(func.lower(Course.name) == name.strip().lower())
        )
        return result.scalar_one_or_none()

    async def search(self, name: str | None = None) -> Sequence[tuple[Course, int]]:
        """Courses, each with how many holes it has entered.

        The count travels with the row because a course with no holes cannot be
        played, and the only place that is discoverable in time is the list you
        pick from. An outer join so a hole-less course still appears — it is
        precisely the one worth showing, marked as such.
        """
        query = (
            select(Course, func.count(Hole.id))
            .outerjoin(Hole, Hole.course_id == Course.id)
            .group_by(Course.id)
            .order_by(Course.name)
        )
        if name:
            query = query.where(Course.name.ilike(f"%{name.strip()}%"))
        result = await self._session.execute(query)
        return [(course, count) for course, count in result.all()]

    async def create(self, created_by: UUID, payload: CourseCreate) -> Course:
        course = Course(
            name=payload.name.strip(),
            location=payload.location,
            created_by=created_by,
        )
        self._session.add(course)
        await self._session.flush()
        await self._session.refresh(course)
        return course

    async def update(self, course: Course, updates: CourseUpdate) -> Course:
        for field, value in updates.model_dump(exclude_unset=True).items():
            setattr(course, field, value.strip() if field == "name" and value else value)
        await self._session.flush()
        await self._session.refresh(course)
        return course

    async def list_holes(self, course_id: UUID) -> Sequence[Hole]:
        result = await self._session.execute(
            select(Hole).where(Hole.course_id == course_id).order_by(Hole.hole_number)
        )
        return result.scalars().all()

    async def upsert_holes(self, course_id: UUID, holes: Sequence[HoleUpsert]) -> Sequence[Hole]:
        """Insert new holes and overwrite existing ones, matched on hole_number.

        Holes absent from the payload are left alone — this adds to a course
        rather than replacing it, so sending holes 4-6 doesn't wipe 1-3.
        """
        existing = {hole.hole_number: hole for hole in await self.list_holes(course_id)}

        for incoming in holes:
            hole = existing.get(incoming.hole_number)
            if hole is None:
                self._session.add(
                    Hole(
                        course_id=course_id,
                        hole_number=incoming.hole_number,
                        par=incoming.par,
                        stroke_index=incoming.stroke_index,
                    )
                )
            else:
                hole.par = incoming.par
                hole.stroke_index = incoming.stroke_index

        await self._session.flush()
        return await self.list_holes(course_id)

    async def holes_belong_to_course(self, course_id: UUID, hole_ids: Sequence[UUID]) -> bool:
        """Whether every id given is a hole of this course.

        Used to stop a round being built from another course's holes — an
        invariant the schema can't express on its own.
        """
        if not hole_ids:
            return True
        result = await self._session.execute(
            select(func.count())
            .select_from(Hole)
            .where(Hole.course_id == course_id, Hole.id.in_(hole_ids))
        )
        return result.scalar_one() == len(set(hole_ids))
