/**
 * The start arithmetic, tested on its own because it is what an organiser
 * believes when they choose how the day runs.
 *
 * A shotgun needs a starting tee per group, and a course only has so many holes.
 * Getting this number wrong on screen does not fail — it produces a day where a
 * third of the field is queueing behind the other two thirds.
 */

import { describe, expect, it } from 'vitest';

import { describeStart, readableGroupSize, startCapacity } from './format';

describe('startCapacity', () => {
  it('makes every hole a starting tee under a shotgun', () => {
    expect(startCapacity(18, 4, 'SHOTGUN')).toEqual({ groups: 18, players: 72 });
  });

  it('cuts disjoint triples under blocks, so a course carries a third as many', () => {
    expect(startCapacity(18, 4, 'BLOCKS')).toEqual({ groups: 6, players: 24 });
  });

  it('leaves a remainder unused under blocks, since a group has to play three', () => {
    expect(startCapacity(8, 3, 'BLOCKS')).toEqual({ groups: 2, players: 6 });
  });

  it('counts a full field of fourballs onto an 18-hole shotgun', () => {
    // The event this exists for: 16 groups fit, and 21 threes would not have.
    const shotgun = startCapacity(18, 4, 'SHOTGUN');
    expect(shotgun!.groups).toBeGreaterThanOrEqual(16);
    expect(startCapacity(18, 3, 'BLOCKS')!.groups).toBeLessThan(21);
  });

  it('has nothing to say about a course too short for one loop', () => {
    expect(startCapacity(2, 3, 'SHOTGUN')).toBeNull();
    expect(startCapacity(0, 3, 'BLOCKS')).toBeNull();
  });
});

describe('describeStart', () => {
  it('names the tee count a shotgun actually gets', () => {
    expect(describeStart(18, 4, 'SHOTGUN')).toContain('starts 18 groups at once');
    expect(describeStart(18, 4, 'SHOTGUN')).toContain('72 players in fourballs');
  });

  it('says how blocks differ, rather than leaving the organiser to divide', () => {
    expect(describeStart(18, 3, 'BLOCKS')).toContain('18 holes make 6');
  });

  it('always says what happens past the ceiling', () => {
    // Neither style refuses a bigger field — it shares loops and staggers, which
    // is a real answer and not an error, so it must not read as a limit.
    expect(describeStart(18, 3, 'SHOTGUN')).toContain('tee off staggered');
    expect(describeStart(18, 3, 'BLOCKS')).toContain('tee off staggered');
  });

  it('stays quiet when the course is too short to say anything useful', () => {
    expect(describeStart(2, 3, 'SHOTGUN')).toBeNull();
  });
});

describe('readableGroupSize', () => {
  it('says what an organiser would say out loud', () => {
    expect(readableGroupSize(3)).toBe('threes');
    expect(readableGroupSize(4)).toBe('fourballs');
  });
});
