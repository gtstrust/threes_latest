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

export type Tournament = {
  id: UUID;
  name: string;
  organiser_id: UUID;
  status: TournamentStatus;
  format: 'ROUND_ROBIN';
  course_id: UUID | null;
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
  course_id: UUID | null;
  status: FunRoundStatus;
  created_at: string;
  updated_at: string;
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
  strokes: number;
  points: number;
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
  total_strokes: number;
  /** Holes actually scored, not the three in the loop — a group still out shows as such. */
  holes_played: number;
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
