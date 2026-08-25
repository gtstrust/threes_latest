/**
 * Turning wire values into something a golfer would say.
 *
 * In their own module rather than beside the components that use them: React
 * Fast Refresh only reloads a file cleanly when it exports components alone.
 */

import type { TournamentStatus } from '../../lib/types';

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
