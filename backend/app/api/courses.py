from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CourseServiceDep, CurrentUserDep, require_course_owner
from app.models.course import Course
from app.schemas.course import (
    CourseCreate,
    CourseRead,
    CourseUpdate,
    CourseWithHoles,
    HoleRead,
    HolesUpsert,
)
from app.services.course import CreatorProfileMissing, DuplicateCourseName

router = APIRouter(prefix="/courses", tags=["courses"])


async def _get_or_404(course_id: UUID, service: CourseServiceDep) -> Course:
    course = await service.get_by_id(course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


@router.post("", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
async def create_course(
    payload: CourseCreate, current_user: CurrentUserDep, service: CourseServiceDep
) -> CourseRead:
    """Create a course. Names are unique without regard to case."""
    try:
        course = await service.create(current_user, payload)
    except CreatorProfileMissing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        ) from None
    except DuplicateCourseName as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CourseRead.model_validate(course)


@router.get("", response_model=list[CourseRead])
async def list_courses(
    current_user: CurrentUserDep,
    service: CourseServiceDep,
    name: str | None = Query(default=None, description="Filter by partial name match"),
) -> list[CourseRead]:
    """Courses are shared, so any authenticated caller can browse them."""
    courses = await service.search(name)
    return [CourseRead.model_validate(course) for course in courses]


@router.get("/{course_id}", response_model=CourseWithHoles)
async def read_course(
    course_id: UUID, current_user: CurrentUserDep, service: CourseServiceDep
) -> CourseWithHoles:
    course = await service.get_with_holes(course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return CourseWithHoles.model_validate(course)


@router.patch("/{course_id}", response_model=CourseRead)
async def update_course(
    course_id: UUID,
    updates: CourseUpdate,
    current_user: CurrentUserDep,
    service: CourseServiceDep,
) -> CourseRead:
    course = await _get_or_404(course_id, service)
    require_course_owner(course, current_user)
    try:
        updated = await service.update(course, updates)
    except DuplicateCourseName as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CourseRead.model_validate(updated)


@router.put("/{course_id}/holes", response_model=list[HoleRead])
async def upsert_holes(
    course_id: UUID,
    payload: HolesUpsert,
    current_user: CurrentUserDep,
    service: CourseServiceDep,
) -> list[HoleRead]:
    """Add or overwrite holes, matched on hole number.

    Additive rather than replacing: sending holes 4-6 leaves 1-3 untouched. A
    3-hole loop only needs the holes it actually plays, so there's no requirement
    to enter all 18 before an event can run.
    """
    course = await _get_or_404(course_id, service)
    require_course_owner(course, current_user)
    holes = await service.upsert_holes(course.id, payload.holes)
    return [HoleRead.model_validate(hole) for hole in holes]
