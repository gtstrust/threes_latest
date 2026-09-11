/**
 * Bracket arithmetic, for telling an organiser what their event will look like.
 *
 * Advice only. The server draws the real thing and `group_sizes` (ADR-004) is
 * authoritative — this mirrors its rule so a number can be shown *before* anyone
 * commits, which is the one moment the organiser can still change the field.
 *
 * The rule mirrored: fill groups of the target size, the leftover becomes its
 * own group, and a player who would be left alone is absorbed into the previous
 * one — splitting it if that would make it oversize.
 */

import type { GroupSize } from '../../lib/types';

const MIN_GROUP_SIZE = 2;
const MAX_GROUP_SIZE = 4;

/** How many groups a field of this size makes. Mirrors `group_sizes` (ADR-004). */
export function groupCount(players: number, target: GroupSize): number {
  if (players < MIN_GROUP_SIZE) return 0;

  const full = Math.floor(players / target);
  const remainder = players % target;

  if (remainder === 0) return full;
  if (remainder >= MIN_GROUP_SIZE) return full + 1;
  // remainder === 1: absorbed into the previous group, which splits in two when
  // that would take it over the maximum — 4 + 1 becomes 3 + 2.
  return target + 1 <= MAX_GROUP_SIZE ? full : full + 1;
}

/**
 * The field size at the start of each knockout round, until one player is left.
 *
 * `[64, 16, 4]` for 64 in fourballs — three rounds, ending in a single group.
 * Empty for a field too small to make a group at all.
 */
export function bracketRounds(players: number, target: GroupSize): number[] {
  const rounds: number[] = [];
  let alive = players;
  // `groupCount` is always fewer than `alive` above one player, because no group
  // is ever left with one — so this terminates rather than merely usually doing.
  while (alive > 1 && rounds.length < 32) {
    const groups = groupCount(alive, target);
    if (groups < 1 || groups >= alive) break;
    rounds.push(alive);
    alive = groups;
  }
  return rounds;
}

/** The bracket as a sentence, or null when the field is too small to describe. */
export function describeBracket(players: number, target: GroupSize): string | null {
  const rounds = bracketRounds(players, target);
  if (rounds.length === 0) return null;

  const groups = rounds.map((alive) => groupCount(alive, target));
  const shape = groups.length === 1 ? `${groups[0]} group` : groups.join(', then ');
  return (
    `${players} players, ${rounds.length} round${rounds.length === 1 ? '' : 's'}: ` +
    `${shape}. One player wins the day.`
  );
}

/**
 * "Champion" or "Out in R2" — how far a player got, for the knockout board.
 *
 * `survived` counts the last round they were drawn into, plus one if they won
 * it, so anything above the rounds actually played means they won the last one.
 * Null on a round robin, where nobody is knocked out.
 */
export function reachedLabel(survived: number | null, roundsPlayed: number): string | null {
  if (survived === null) return null;
  if (survived > roundsPlayed) return 'Champion';
  return `Out in R${survived}`;
}
