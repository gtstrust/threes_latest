from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import CurrentUser, decode_supabase_jwt
from app.models.course import Course
from app.models.round import Group
from app.models.tournament import Tournament, TournamentKind
from app.services.course import CourseService
from app.services.fun_round import FunRoundService
from app.services.leaderboard import LeaderboardService
from app.services.mail import Mailer, build_mailer
from app.services.participant import ParticipantService
from app.services.player import PlayerService
from app.services.realtime import RealtimeNotifier, build_notifier
from app.services.reminders import ReminderService
from app.services.round import RoundService
from app.services.score_entry import ScoreEntryService
from app.services.tournament import TournamentService

# The description is what Swagger shows inside its Authorize dialog, which is
# where someone reading /docs actually asks this question — and the honest answer
# is unusual enough to be worth putting there: there is no login endpoint on this
# API to call, because Supabase issues tokens straight to the client.
_bearer_scheme = HTTPBearer(
    description=(
        "A Supabase access token. This API never sees a password and has no login "
        "endpoint — sign in through Supabase Auth (magic link) and send the "
        "access_token it returns. GET /auth/me verifies one without touching the "
        "database, so it is the quickest check that a token works. For local work, "
        "mint one with `python scripts/dev_token.py --email you@example.com`."
    )
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
) -> CurrentUser:
    return await decode_supabase_jwt(credentials.credentials)


async def get_player_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlayerService:
    return PlayerService(session)


async def get_tournament_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TournamentService:
    return TournamentService(session)


async def get_course_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CourseService:
    return CourseService(session)


async def get_participant_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ParticipantService:
    return ParticipantService(session)


async def get_round_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RoundService:
    return RoundService(session)


async def get_fun_round_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> FunRoundService:
    return FunRoundService(session)


async def get_score_entry_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ScoreEntryService:
    return ScoreEntryService(session)


async def get_leaderboard_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> LeaderboardService:
    return LeaderboardService(session)


async def get_mailer() -> Mailer:
    """The mail sender — a no-op unless a provider is configured.

    A dependency rather than a module-level singleton for the same reason
    `get_realtime_notifier` is one: `tests/conftest.py` overrides it so the suite
    can never send real mail, whatever a developer's `.env` happens to hold.
    """
    return build_mailer()


async def get_reminder_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    mailer: Annotated[Mailer, Depends(get_mailer)],
) -> ReminderService:
    return ReminderService(session, mailer)


async def get_realtime_notifier() -> RealtimeNotifier:
    """The Realtime signal sender — a no-op unless Supabase is configured.

    A dependency rather than a module-level singleton so tests can swap it through
    `app.dependency_overrides`, exactly as they already do for `get_db`. It takes
    no session: the signal carries no data (ADR-010), so there is nothing to read.
    """
    return build_notifier()


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
PlayerServiceDep = Annotated[PlayerService, Depends(get_player_service)]
TournamentServiceDep = Annotated[TournamentService, Depends(get_tournament_service)]
CourseServiceDep = Annotated[CourseService, Depends(get_course_service)]
ParticipantServiceDep = Annotated[ParticipantService, Depends(get_participant_service)]
RoundServiceDep = Annotated[RoundService, Depends(get_round_service)]
FunRoundServiceDep = Annotated[FunRoundService, Depends(get_fun_round_service)]
ScoreEntryServiceDep = Annotated[ScoreEntryService, Depends(get_score_entry_service)]
LeaderboardServiceDep = Annotated[LeaderboardService, Depends(get_leaderboard_service)]
RealtimeNotifierDep = Annotated[RealtimeNotifier, Depends(get_realtime_notifier)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]
ReminderServiceDep = Annotated[ReminderService, Depends(get_reminder_service)]


def require_course_owner(course: Course, current_user: CurrentUser) -> None:
    """Guard edits to a course.

    Courses are shared reference data — anyone may read one and link a tournament
    to it — but only whoever created it may change its name or holes, so one
    organiser can't renumber a course out from under another's live event.
    """
    if course.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the player who created this course can change it",
        )


def reject_fun_round(tournament: Tournament) -> None:
    """Refuse a fun round on a tournament-management route.

    A fun round is a `tournaments` row, so it would otherwise be reachable through
    the tournament endpoints — where it could be hand-driven through the raw ADR-003
    state machine, or have its single-group cap bypassed by self-registering. Those
    routes therefore treat a fun round as not found; it is driven via `/fun-rounds`.
    """
    if tournament.kind is TournamentKind.FUN_ROUND:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")


def require_organiser(tournament: Tournament, current_user: CurrentUser) -> None:
    """Guard actions only a tournament's organiser may take.

    Until now the only authorization in the app was "holds a valid JWT". Anything
    that changes a tournament — its details, its status, and later its rounds —
    goes through here rather than through ad-hoc checks in each route.
    """
    if tournament.organiser_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organiser of this tournament can do that",
        )


async def require_can_view(
    tournament: Tournament,
    current_user: CurrentUser,
    participants: ParticipantService,
) -> None:
    """Guard reading a tournament: the organiser, or anyone in the field.

    Async because unlike the other guards this can't be answered from the
    tournament row alone — it has to look for the caller's place in the field.
    """
    if tournament.organiser_id == current_user.id:
        return

    if await participants.get_for_player(tournament.id, current_user.id) is not None:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the organiser and players in this tournament can view it",
    )


async def require_group_member(
    group: Group,
    tournament: Tournament,
    current_user: CurrentUser,
    participants: ParticipantService,
) -> None:
    """Guard entering scores for a group: someone in it, or the organiser.

    Any member scores for the whole group, which is what makes a Virtual Player
    playable — somebody with no account is entered by whoever they are walking
    round with. The organiser is allowed too, as the way back when a group's only
    phone dies mid-round; without that the card would be unrecoverable.

    Async for the same reason as require_can_view: it has to look the caller up in
    the field before it can find their place in the group.
    """
    if tournament.organiser_id == current_user.id:
        return

    participant = await participants.get_for_player(tournament.id, current_user.id)
    if participant is not None and participant.id in {
        member.participant_id for member in group.members
    }:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only players in this group and the organiser can enter its scores",
    )
