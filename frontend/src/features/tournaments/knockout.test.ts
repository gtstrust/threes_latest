/**
 * The bracket sentence an organiser reads before they commit to a field size.
 *
 * Worth testing on its own because it is the only place the app predicts what
 * the server will do. If it drifts from `group_sizes` (ADR-004) it will not
 * fail — it will quietly promise an event that does not happen.
 */

import { describe, expect, it } from 'vitest';

import { bracketRounds, describeBracket, groupCount, reachedLabel } from './knockout';

describe('groupCount', () => {
  it('matches the ADR-004 rule for fourballs', () => {
    expect(groupCount(64, 4)).toBe(16);
    expect(groupCount(16, 4)).toBe(4);
    expect(groupCount(4, 4)).toBe(1);
    expect(groupCount(5, 4)).toBe(2); // 4 + 1 splits into 3 + 2
    expect(groupCount(9, 4)).toBe(3); // 4, 3, 2
  });

  it('matches it for threes, where a leftover player makes a fourball', () => {
    expect(groupCount(7, 3)).toBe(2); // 3 + 4, not 3 + 3 + 1
    expect(groupCount(5, 3)).toBe(2); // 3 + 2
    expect(groupCount(9, 3)).toBe(3);
  });

  it('has nothing to make from fewer than two players', () => {
    expect(groupCount(1, 4)).toBe(0);
    expect(groupCount(0, 4)).toBe(0);
  });
});

describe('bracketRounds', () => {
  it('collapses 64 fourballs in three rounds', () => {
    // The event ADR-012 exists for: 64 is 4 * 4 * 4.
    expect(bracketRounds(64, 4)).toEqual([64, 16, 4]);
  });

  it('needs a fourth round for one more player', () => {
    expect(bracketRounds(65, 4)).toHaveLength(4);
  });

  it('always terminates', () => {
    for (let players = 2; players <= 200; players++) {
      for (const target of [3, 4] as const) {
        const rounds = bracketRounds(players, target);
        expect(rounds[0]).toBe(players);
        // Strictly shrinking, so it can never loop.
        rounds.forEach((alive, index) => {
          if (index > 0) expect(alive).toBeLessThan(rounds[index - 1]);
        });
      }
    }
  });

  it('says nothing about a field too small to play', () => {
    expect(bracketRounds(1, 4)).toEqual([]);
  });
});

describe('describeBracket', () => {
  it('spells out the shape the organiser is about to commit to', () => {
    expect(describeBracket(64, 4)).toBe(
      '64 players, 3 rounds: 16, then 4, then 1. One player wins the day.',
    );
  });

  it('handles a field that is already one group', () => {
    expect(describeBracket(4, 4)).toBe('4 players, 1 round: 1 group. One player wins the day.');
  });

  it('stays quiet rather than describing an event that cannot run', () => {
    expect(describeBracket(1, 4)).toBeNull();
  });
});

describe('reachedLabel', () => {
  it('names the champion, who outlasted the rounds themselves', () => {
    expect(reachedLabel(4, 3)).toBe('Champion');
  });

  it('says which round everyone else went out in', () => {
    expect(reachedLabel(3, 3)).toBe('Out in R3');
    expect(reachedLabel(1, 3)).toBe('Out in R1');
  });

  it('says nothing on a round robin, where nobody is knocked out', () => {
    expect(reachedLabel(null, 3)).toBeNull();
  });
});
