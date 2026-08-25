/**
 * What to ask the group next, given what the server made of their strokes.
 *
 * Pure — no fetching, no rendering, plain data in and out. That mirrors
 * `backend/app/services/scoring.py`, which is pure for the same reason: this is
 * the platform's most important rule and it should be testable exhaustively
 * without a fixture in sight.
 *
 * **The server owns the decision** (ADR-002). This module never works out who
 * won a hole; it reads what the server already decided and answers the narrower
 * question of what the app should put on screen.
 *
 * ## Why the caller has to remember what it asked
 *
 * Read `score_hole` and the shape falls out: a `closest_to_pin` that names a
 * tied player **always** decides the hole. So the server never returns "you gave
 * me a pin answer and they are still level" — `closest_to_pin_participant_id` is
 * populated only on a hole that is settled, and a hole that is still tied
 * carries no record of what has been asked.
 *
 * The unresolved state therefore lives here. A group reaches longest drive only
 * by *declining* the pin question — "none of us reached the green" — and nothing
 * in the response can express that, because nothing was sent. Hence `Asked`.
 */

import type { HoleResult, UUID } from '../../lib/types';

/**
 * Which questions this group has already been put, and waved away.
 *
 * Not derived from the response, because it cannot be — see above.
 */
export type Asked = {
  closestToPin: boolean;
  longestDrive: boolean;
};

export const NOTHING_ASKED: Asked = { closestToPin: false, longestDrive: false };

export type Prompt =
  /** Settled: an outright winner, a tie-break answer, or nobody. Stop asking. */
  | { kind: 'settled'; result: HoleResult }
  /** Ask these players — and only these — who was closest to the pin. */
  | { kind: 'ask_closest_to_pin'; candidates: UUID[] }
  /** Still level. Ask the same players who hit the longest drive on the fairway. */
  | { kind: 'ask_longest_drive'; candidates: UUID[] }
  /** Both questions declined and they are still level, so the hole goes unwon. */
  | { kind: 'nobody_wins'; candidates: UUID[] };

export function nextPrompt(result: HoleResult, asked: Asked): Prompt {
  // The server populates `tied_participants` only while a tie is unresolved, so
  // an empty list means the hole is decided however it was decided.
  if (result.tied_participants.length === 0) {
    return { kind: 'settled', result };
  }

  const candidates = result.tied_participants;

  if (!asked.closestToPin) return { kind: 'ask_closest_to_pin', candidates };
  if (!asked.longestDrive) return { kind: 'ask_longest_drive', candidates };

  // Both declined. ADR-007: holes are never halved, so the alternative to one
  // winner is none — and the hole is already stored that way. There is nothing
  // left to submit, which is why this is distinct from a question.
  return { kind: 'nobody_wins', candidates };
}

/**
 * The strokes as a map, for re-submitting a hole.
 *
 * A tie-break answer arrives by posting the *same hole again* with the same
 * strokes plus the answer — there is no separate endpoint, because that single
 * upsert path is also how a mis-keyed number is corrected (ADR-009).
 */
export function strokesFrom(result: HoleResult): Record<UUID, number> {
  return Object.fromEntries(result.scores.map((score) => [score.participant_id, score.strokes]));
}

/** Whether a hole has been scored at all, for showing a card's progress. */
export function isScored(result: HoleResult | undefined): result is HoleResult {
  return result !== undefined;
}
