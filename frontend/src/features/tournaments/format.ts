/**
 * Turning wire values into something a golfer would say.
 *
 * In their own module rather than beside the components that use them: React
 * Fast Refresh only reloads a file cleanly when it exports components alone.
 */

import type { GroupSize, LoopStyle, TournamentStatus } from '../../lib/types';

/** `REGISTRATION_OPEN` is the wire format, not something to put on screen. */
export function readableStatus(status: TournamentStatus): string {
  return {
    CREATED: 'Not open yet',
    REGISTRATION_OPEN: 'Registration open',
    REGISTRATION_CLOSED: 'Registration closed',
    ROUND_IN_PROGRESS: 'Playing',
    ROUND_COMPLETE: 'Round complete',
    TOURNAMENT_COMPLETE: 'Finished',
  }[status];
}

/**
 * Read "7, 8, 9" — or "7 8 9", or blank — into hole numbers.
 *
 * Lenient about separators on purpose: this is typed on a phone, outdoors,
 * probably one-handed. The API validates properly and its refusals are worded
 * for a human, so there is nothing to gain by second-guessing it here.
 */
export function parseHoles(text: string): number[] {
  return text
    .split(/[^0-9]+/)
    .filter(Boolean)
    .map(Number);
}

/** A loop is three holes, wherever that number is needed on screen. */
const HOLES_PER_LOOP = 3;

/** "Fourballs" / "threes" — what an organiser calls the group size out loud. */
export function readableGroupSize(size: GroupSize | number): string {
  return size === 4 ? 'fourballs' : 'threes';
}

/**
 * How many groups this course can start at once, and how many players that is.
 *
 * The arithmetic an organiser cannot do at the sign-up sheet, and the thing that
 * decides whether their day is a real shotgun or a queue. Under SHOTGUN every
 * hole is a starting tee, so a course starts as many groups as it has holes;
 * under BLOCKS the holes are cut into disjoint 3-hole loops, so it starts a
 * third as many. Either way, groups beyond that share and tee off staggered.
 *
 * Returns null when the course cannot make even one loop, where there is nothing
 * useful to say and the form already says the course is too short.
 */
export function startCapacity(
  holes: number,
  groupSize: GroupSize | number,
  style: LoopStyle,
): { groups: number; players: number } | null {
  if (holes < HOLES_PER_LOOP) return null;
  const groups = style === 'SHOTGUN' ? holes : Math.floor(holes / HOLES_PER_LOOP);
  return { groups, players: groups * groupSize };
}

/**
 * That capacity as a sentence, for the organiser choosing how the day starts.
 *
 * Null when the course is too short to say anything useful — the form already
 * tells them a loop needs three holes, and repeating it here would not help.
 */
export function describeStart(
  holes: number,
  groupSize: GroupSize | number,
  style: LoopStyle,
): string | null {
  const capacity = startCapacity(holes, groupSize, style);
  if (!capacity) return null;

  const field = `${capacity.groups} groups at once — ${capacity.players} players in ${readableGroupSize(groupSize)}`;
  const shared = 'Beyond that, groups share a loop and tee off staggered.';

  return style === 'SHOTGUN'
    ? `A shotgun needs a tee per group. This course has ${holes} holes, so it starts ${field}. ${shared}`
    : `The course is cut into 3-hole loops, and ${holes} holes make ${capacity.groups}. That starts ${field}. ${shared}`;
}
