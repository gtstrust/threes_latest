from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.core.deps import (
    CurrentUserDep,
    PlayerServiceDep,
    StatsServiceDep,
    TournamentServiceDep,
)
from app.schemas.player import PlayerRead, PlayerUpdate, ProvisionProfile, ReferralsRead
from app.schemas.stats import CourseRecordRead, PlayerStatsRead
from app.schemas.tournament import TournamentRead

router = APIRouter(prefix="/players", tags=["players"])


@router.post("", response_model=PlayerRead)
async def provision_profile(
    current_user: CurrentUserDep,
    player_service: PlayerServiceDep,
    payload: ProvisionProfile | None = None,
) -> PlayerRead:
    """Idempotently ensure a profile row exists for the authenticated user.

    Intended to be called once by the client immediately after Supabase
    magic-link login. Safe to call repeatedly.

    `referral_code` is honoured **only when the row is created**. This is called
    on every login, so attributing an existing profile would let the last person
    to send a link claim a player who has been here for months.
    """
    player = await player_service.get_or_create_profile(
        current_user, payload.referral_code if payload else None
    )
    return PlayerRead.model_validate(player)


@router.get("/me", response_model=PlayerRead)
async def read_my_profile(
    current_user: CurrentUserDep, player_service: PlayerServiceDep
) -> PlayerRead:
    player = await player_service.get_by_id(current_user.id)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        )
    return PlayerRead.model_validate(player)


@router.patch("/me", response_model=PlayerRead)
async def update_my_profile(
    updates: PlayerUpdate,
    current_user: CurrentUserDep,
    player_service: PlayerServiceDep,
) -> PlayerRead:
    player = await player_service.get_by_id(current_user.id)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        )
    updated = await player_service.update_profile(player, updates)
    return PlayerRead.model_validate(updated)


@router.get("/me/tournaments", response_model=list[TournamentRead])
async def list_my_tournaments(
    current_user: CurrentUserDep, tournaments: TournamentServiceDep
) -> list[TournamentRead]:
    """Tournaments the caller is *playing in*, newest first.

    Distinct from `GET /tournaments`, which lists what they organise. Without
    this a player has no way to find an event: they can read one by id, since
    `require_can_view` admits the field, but nothing tells them the id — so
    losing the invitation link would strand them mid-day.

    Virtual players never appear here. They have no account to call the API with.
    """
    playing = await tournaments.list_for_player(current_user.id)
    # for_viewer, not model_validate: these are events the caller plays in but
    # mostly does not run, and the join code is the organiser's to hand out.
    return [TournamentRead.for_viewer(tournament, current_user.id) for tournament in playing]


@router.get("/{player_id}", response_model=PlayerRead)
async def read_player(
    player_id: UUID, current_user: CurrentUserDep, player_service: PlayerServiceDep
) -> PlayerRead:
    player = await player_service.get_by_id(player_id)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    return PlayerRead.model_validate(player)


@router.get("/me/referrals", response_model=ReferralsRead)
async def read_my_referrals(
    current_user: CurrentUserDep, player_service: PlayerServiceDep
) -> ReferralsRead:
    """The caller's own referral code, and how many players arrived through it."""
    player = await player_service.get_by_id(current_user.id)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profile yet — call POST /players first",
        )
    return ReferralsRead(
        referral_code=player.referral_code,
        players_referred=await player_service.count_referred(player.id),
    )


@router.get("/me/stats/courses", response_model=list[CourseRecordRead])
async def read_my_course_records(
    current_user: CurrentUserDep, stats: StatsServiceDep
) -> list[CourseRecordRead]:
    """The caller's record at each course they've played, hole by hole.

    Separate from `/me/stats` rather than folded into it: this grows with every
    course somebody plays, while the career figures and recent history do not,
    and the page that opens on sign-in should not pay for a section further down
    it. Own data only, so the caller's id is the filter and there is no guard to
    add beyond the bearer token.
    """
    return [
        CourseRecordRead.from_figures(figures)
        for figures in await stats.courses_for_player(current_user.id)
    ]


@router.get("/me/stats", response_model=PlayerStatsRead)
async def read_my_stats(current_user: CurrentUserDep, stats: StatsServiceDep) -> PlayerStatsRead:
    """The caller's own record: career figures and their recent events.

    No authorization guard beyond the bearer token, because there is nothing to
    guard against — the caller's own id *is* the filter, so there is no id to
    substitute for somebody else's. Reading another player's record is not a
    permission this endpoint refuses; it is a thing it cannot express.

    A player with no profile still gets an answer: an empty history and zeroes,
    which is what somebody who has signed up and played nothing should see.
    """
    return PlayerStatsRead.from_stats(await stats.for_player(current_user.id))
