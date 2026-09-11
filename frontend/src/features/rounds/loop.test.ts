/**
 * The labelling rule, tested on its own because getting it wrong is silent.
 *
 * A hole number that is merely *missing* shows up immediately — a blank space on
 * screen. A hole number that is confidently wrong does not: "1" looks exactly
 * like a hole number, and the player only finds out when they arrive at a tee
 * with somebody else's group on it.
 */

import { describe, expect, it } from 'vitest';

import { loopHoles, loopLabel } from './loop';
import type { CourseWithHoles } from '../../lib/types';

const COURSE = {
  id: 'course-1',
  name: 'Royal Melbourne',
  location: null,
  created_by: 'player-1',
  created_at: '',
  updated_at: '',
  holes: [7, 8, 9].map((hole_number) => ({
    id: `h${hole_number}`,
    course_id: 'course-1',
    hole_number,
    par: null,
    stroke_index: null,
  })),
} as CourseWithHoles;

/** Deliberately out of order — the API does not promise a sorted list. */
const HOLES = [
  { hole_id: 'h9', sequence: 3 },
  { hole_id: 'h7', sequence: 1 },
  { hole_id: 'h8', sequence: 2 },
];

describe('loopHoles', () => {
  it('labels each hole with the number the course calls it', () => {
    expect(loopHoles(HOLES, COURSE).map((hole) => hole.label)).toEqual([7, 8, 9]);
  });

  it('puts the loop in playing order', () => {
    expect(loopHoles(HOLES, COURSE).map((hole) => hole.holeId)).toEqual(['h7', 'h8', 'h9']);
  });

  it('falls back to the position in the loop when the course is not loaded', () => {
    // Score entry must not wait on the course: a group standing on a green with
    // one bar of signal has to be able to key a number in regardless.
    const loop = loopHoles(HOLES);
    expect(loop.map((hole) => hole.label)).toEqual([1, 2, 3]);
    expect(loop.every((hole) => hole.known)).toBe(false);
  });

  it('marks a real hole number as known and a fallback as not', () => {
    expect(loopHoles(HOLES, COURSE).every((hole) => hole.known)).toBe(true);
  });

  it('falls back per hole when the course is missing one', () => {
    // A course whose holes were re-entered can leave a group pointing at a hole
    // id that no longer exists. The rest of the loop is still nameable.
    const partial = { ...COURSE, holes: COURSE.holes.filter((hole) => hole.id !== 'h8') };
    expect(loopHoles(HOLES, partial)).toEqual([
      { holeId: 'h7', label: 7, known: true },
      { holeId: 'h8', label: 2, known: false },
      { holeId: 'h9', label: 9, known: true },
    ]);
  });

  it('has nothing to say about an empty loop', () => {
    expect(loopHoles([], COURSE)).toEqual([]);
  });
});

describe('loopLabel', () => {
  it('names the holes when every one of them is known', () => {
    expect(loopLabel(loopHoles(HOLES, COURSE))).toBe('Holes 7, 8, 9');
  });

  it('says nothing rather than guessing when the course is not loaded', () => {
    // The whole point: "Holes 1, 2, 3" would be a sentence about the course, and
    // it would be false. Silence is recoverable; a wrong tee is not.
    expect(loopLabel(loopHoles(HOLES))).toBeNull();
  });

  it('says nothing when even one hole is unknown', () => {
    const partial = { ...COURSE, holes: COURSE.holes.filter((hole) => hole.id !== 'h8') };
    expect(loopLabel(loopHoles(HOLES, partial))).toBeNull();
  });

  it('says nothing for an empty loop', () => {
    expect(loopLabel([])).toBeNull();
  });
});

describe('a loop that wraps the turn', () => {
  // The case the draw could not express until ADR-011. On an 18-hole shotgun the
  // group starting on the 17th plays 17, 18, 1 — so hole-number order and
  // playing order disagree, which is the whole reason `loopHoles` sorts by
  // `sequence`. Every other test here uses an ascending loop, where a sort by
  // number would have looked correct.
  const FULL_COURSE = {
    ...COURSE,
    holes: Array.from({ length: 18 }, (_, index) => ({
      id: `h${index + 1}`,
      course_id: 'course-1',
      hole_number: index + 1,
      par: null,
      stroke_index: null,
    })),
  } as CourseWithHoles;

  const WRAPPED = [
    { hole_id: 'h1', sequence: 3 },
    { hole_id: 'h17', sequence: 1 },
    { hole_id: 'h18', sequence: 2 },
  ];

  it('keeps playing order rather than sorting by hole number', () => {
    expect(loopHoles(WRAPPED, FULL_COURSE).map((hole) => hole.label)).toEqual([17, 18, 1]);
  });

  it('starts on the tee the group actually walks to', () => {
    // Not hole 1, which is where a sort by number would have sent them — and
    // where another group is already standing.
    expect(loopHoles(WRAPPED, FULL_COURSE)[0].label).toBe(17);
  });

  it('names the holes in the order they are played', () => {
    expect(loopLabel(loopHoles(WRAPPED, FULL_COURSE))).toBe('Holes 17, 18, 1');
  });
});
