/**
 * A group's loop, labelled with the holes a golfer would recognise.
 *
 * The draw is a shotgun start: every group tees off at once on a different
 * triple, so "which hole am I starting on" is the first thing a player needs and
 * the only one they cannot work out from anything else on screen.
 *
 * The sort below is by `sequence`, never by hole number, and that is load-bearing
 * rather than incidental: a shotgun loop can wrap the turn (ADR-011), so the group
 * starting on the 17th plays 17, 18, 1. Sorting those by number would read "1, 17,
 * 18" and send the group to a tee three holes away with somebody already on it.
 *
 * The app deals in hole *ids*, and the position in the loop (1, 2, 3) is its own
 * bookkeeping rather than anything a player recognises. A group playing 7-9 is
 * standing on the 7th tee, and a screen that says "1" is not simplifying — it is
 * naming a different hole, on a course where the 1st tee is somewhere else
 * entirely with another group already on it.
 *
 * `known` is what stops that mistake being re-made anywhere downstream: the
 * label falls back to the loop position so score entry still works while the
 * course request is in flight or has failed, but callers that would be *making a
 * claim about the course* — "Holes 7, 8, 9" — check `known` first and say
 * nothing rather than something false.
 */

import type { CourseWithHoles, GroupHole, UUID } from '../../lib/types';

export type LoopHole = {
  holeId: UUID;
  /** The course's own hole number when known, else the position in the loop. */
  label: number;
  /** Whether `label` is the course's hole number rather than a fallback. */
  known: boolean;
};

/**
 * The loop in playing order, each hole labelled.
 *
 * @param holes - The group's holes, in any order.
 * @param course - The course, once loaded. Absent while it is still in flight.
 * @returns One entry per hole, sorted by `sequence`.
 */
export function loopHoles(
  holes: GroupHole[],
  course?: CourseWithHoles | null,
): LoopHole[] {
  const numberOf = new Map(
    course?.holes.map((hole) => [hole.id, hole.hole_number]) ?? [],
  );

  return [...holes]
    .sort((a, b) => a.sequence - b.sequence)
    .map((hole, index) => {
      const number = numberOf.get(hole.hole_id);
      return {
        holeId: hole.hole_id,
        label: number ?? index + 1,
        known: number !== undefined,
      };
    });
}

/**
 * "Holes 7, 8, 9" — or null when the course has not resolved the numbers.
 *
 * Null rather than a positional guess: this string is read on a first tee, and
 * the whole point of a shotgun start is that the group is not on the 1st.
 */
export function loopLabel(loop: LoopHole[]): string | null {
  if (loop.length === 0 || !loop.every((hole) => hole.known)) return null;
  return `Holes ${loop.map((hole) => hole.label).join(', ')}`;
}
