/**
 * The API contract, mirrored from `backend/app/schemas/`.
 *
 * Hand-written rather than generated. The surface is about twenty types and the
 * backend is in the same repository, so a generator would add a build step and a
 * stale-artefact problem to save very little. If this list ever outgrows a
 * single screen, generate it from the OpenAPI schema at `/openapi.json` instead
 * of letting it drift.
 */

export type UUID = string;

/** ADR-003. Values match their names on the wire — and they are UPPERCASE. */
export type TournamentStatus =
  | 'CREATED'
  | 'REGISTRATION_OPEN'
  | 'REGISTRATION_CLOSED'
  | 'ROUND_IN_PROGRESS'
  | 'ROUND_COMPLETE'
  | 'TOURNAMENT_COMPLETE';

export type RoundStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETE';

/** Which level of the ADR-007 cascade settled a hole. Lowercase, unlike the statuses. */
export type DecidedBy = 'strokes' | 'closest_to_pin' | 'longest_drive' | 'no_winner';

export type Player = {
  id: UUID;
  email: string | null;
  display_name: string | null;
  created_at: string;
  updated_at: string;
};

export type Hole = {
  id: UUID;
  course_id: UUID;
  hole_number: number;
  par: number | null;
  stroke_index: number | null;
};

export type Course = {
  id: UUID;
  name: string;
  location: string | null;
  created_by: UUID;
  created_at: string;
  updated_at: string;
};

export type CourseWithHoles = Course & { holes: Hole[] };

/**
 * A course as `GET /courses` lists it. `hole_count` rides along because a course
 * with no holes entered cannot be played, and the list is the last point at which
 * that is worth finding out.
 */
export type CourseSummary = Course & { hole_count: number };

/** The two targets an organiser may pick; the draw absorbs remainders itself. */
export type GroupSize = 3 | 4;

export type LoopStyle = 'BLOCKS' | 'SHOTGUN';

/**
 * How a tournament's rounds relate to each other (ADR-012).
 *
 * ROUND_ROBIN redraws the whole field every round and the leaderboard adds up.
 * KNOCKOUT makes each group a match: one player goes through and the rest are
 * out, so the field shrinks every round.
 */
export type TournamentFormat = 'ROUND_ROBIN' | 'KNOCKOUT';

/** Which level of the knockout cascade sent a player through (ADR-012). */
export type AdvancedBy = 'points' | 'strokes' | 'countback' | 'organiser';

export type Tournament = {
  id: UUID;
  name: string;
  organiser_id: UUID;
  /** The invitation — null unless you're the organiser, whose code it is to hand out. */
  join_code: string | null;
  /** Optional ceiling on the field. Null means no cap; it only binds self-registration. */
  max_players: number | null;
  status: TournamentStatus;
  format: TournamentFormat;
  /** Players per group the draw aims for: 3, the format, or 4 for fourballs (ADR-004). */
  group_size: number;
  /**
   * How the holes in play become loops (ADR-011). BLOCKS cuts disjoint triples,
   * so 18 holes make 6 loops; SHOTGUN makes every hole a starting tee, so they
   * make 18 and the whole field tees off at once.
   */
  loop_style: LoopStyle;
  /** Decide holes on net strokes rather than gross (ADR-013). Off by default. */
  handicap_enabled: boolean;
  course_id: UUID | null;
  /**
   * When it's played, as an instant. Null means no date — and an event with no
   * date is one the day-before reminder sweep never finds, which is why this is
   * worth setting even though nothing about play depends on it.
   */
  scheduled_at: string | null;
  created_at: string;
  updated_at: string;
};

/**
 * A Fun Round — a casual, self-run round (Phase 2). It is a tournament under the
 * hood, but the client sees a simpler three-state lifecycle, not the ADR-003
 * machine: a `lobby` you fill, a round you're `playing`, a `finished` card.
 */
export type FunRoundStatus = 'lobby' | 'playing' | 'finished';

export type FunRound = {
  id: UUID;
  name: string;
  host_id: UUID;
  /** The invitation. Everyone in a fun round has it — pulling in a fourth is the point. */
  join_code: string;
  course_id: UUID | null;
  /** The loop chosen at setup. Null means the draw takes the first three holes. */
  hole_numbers: number[] | null;
  status: FunRoundStatus;
  created_at: string;
  updated_at: string;
};

/**
 * What someone sent the link sees before they join — the one fun-round read that
 * isn't players-only, since guarding it would refuse the very people invited.
 * Deliberately carries no field and no draw.
 */
export type FunRoundPreview = {
  id: UUID;
  name: string;
  host_name: string;
  player_count: number;
  is_full: boolean;
  status: FunRoundStatus;
};

/** A fun round with its field and — once started — its single drawn group. */
export type FunRoundDetail = FunRound & {
  participants: Participant[];
  round: RoundWithGroups | null;
};

export type Participant = {
  id: UUID;
  tournament_id: UUID;
  /** Null for a Virtual Player — someone with no account, scored by their group. */
  player_id: UUID | null;
  display_name: string;
  is_virtual: boolean;
  /** Per event, 0-54, null until somebody enters one (ADR-013). */
  playing_handicap: number | null;
  created_at: string;
  updated_at: string;
};

export type GroupMember = { participant_id: UUID };
export type GroupHole = { hole_id: UUID; sequence: number };

/** One match: 2–4 players on one 3-hole loop (ADR-004). */
export type Group = {
  id: UUID;
  round_id: UUID;
  group_number: number;
  members: GroupMember[];
  holes: GroupHole[];
  /** Who goes through, on a knockout. Null on a round robin, and null on a
   *  knockout group nothing could separate — which is what the organiser
   *  resolves (ADR-012). */
  advancing_participant_id: UUID | null;
  advanced_by: AdvancedBy | null;
};

export type Round = {
  id: UUID;
  tournament_id: UUID;
  round_number: number;
  status: RoundStatus;
  created_at: string;
  updated_at: string;
};

export type RoundWithGroups = Round & { groups: Group[] };

export type HoleScore = {
  participant_id: UUID;
  /** Gross — what the group counted. */
  strokes: number;
  points: number;
  /** Shots this player's handicap gave them here. Net is the difference (ADR-013). */
  strokes_received: number;
};

export type HoleResult = {
  hole_id: UUID;
  winner_participant_id: UUID | null;
  decided_by: DecidedBy;
  closest_to_pin_participant_id: UUID | null;
  longest_drive_participant_id: UUID | null;
  scores: HoleScore[];
  /**
   * Who the group still has to separate, and the whole reason score entry is a
   * conversation rather than a form. Empty unless the strokes tied and no
   * tie-break answer has settled it yet. Ask *only* these players (ADR-007) —
   * naming anyone else is a 422, not a silent no-op.
   */
  tied_participants: UUID[];
  created_at: string;
  updated_at: string;
};

export type GroupCard = { group_id: UUID; holes: HoleResult[] };

export type LeaderboardEntry = {
  /** Repeats for players genuinely level, and the next position skips: 1, 2, 2, 4. */
  position: number;
  participant_id: UUID;
  display_name: string;
  points: number;
  /** Gross. Unchanged in meaning, so this still reads as it always did. */
  total_strokes: number;
  /** Holes actually scored, not the three in the loop — a group still out shows as such. */
  holes_played: number;
  /** Gross less shots received, and what the board was actually ranked on
   *  (ADR-013). Null on a scratch event — a number equal to `total_strokes`
   *  would read as a real net score rather than as "not applicable". */
  net_strokes: number | null;
  /** Rounds survived, on a **knockout** — the last round drawn into, plus one if
   *  they won it, so the champion leads (ADR-012). Null on a round robin, where
   *  nobody is knocked out and the figure would mean nothing. */
  rounds_survived: number | null;
};

export type Leaderboard = {
  tournament_id: UUID;
  /** Null on the cumulative tournament board. */
  round_id: UUID | null;
  entries: LeaderboardEntry[];
};

/** The payload of a realtime ping. Carries no scores, by design (ADR-010). */
export type LeaderboardChanged = {
  tournament_id: UUID;
  round_id: UUID;
};

/**
 * An invitation, resolved from its code — the one read open to someone with no
 * relationship to the event yet, which is what makes a shared link work.
 *
 * `kind` says where accepting lands you: a tournament and a fun round are
 * different screens even though they are the same row underneath.
 */
export type JoinPreview = {
  kind: 'tournament' | 'fun_round';
  id: UUID;
  name: string;
  host_name: string;
  player_count: number;
  /** False once registration closes, or a fun round's single group is full. */
  can_join: boolean;
  status: TournamentStatus;
};

/** Your own referral code, and what it has brought in. Attribution only. */
export type Referrals = { referral_code: string; players_referred: number };

/** Career figures, computed server-side so two clients can't divide differently. */
export type Career = {
  events_played: number;
  holes_played: number;
  /** Holes taken. Points and holes won are the same count — ADR-007 has no halves. */
  holes_won: number;
  total_strokes: number;
  win_rate: number;
  average_strokes: number;
};

export type HistoryEntry = {
  tournament_id: UUID;
  name: string;
  kind: 'TOURNAMENT' | 'FUN_ROUND';
  status: TournamentStatus;
  played_at: string;
  /** Null until they've scored a hole — in it, but with no placing yet. */
  position: number | null;
  points: number;
  total_strokes: number;
  holes_played: number;
};

export type PlayerStats = { career: Career; history: HistoryEntry[] };

/** Your record on one hole of one course, over every time you've played it. */
export type HoleRecord = {
  hole_number: number;
  times_played: number;
  holes_won: number;
  best_strokes: number;
  average_strokes: number;
};

export type CourseRecord = {
  course_id: UUID;
  course_name: string;
  rounds_played: number;
  holes_played: number;
  holes_won: number;
  average_strokes: number;
  holes: HoleRecord[];
};
