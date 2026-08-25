/**
 * Every path through ADR-007, driven by responses shaped like the real API's.
 *
 * The fixtures match what `POST /groups/{id}/holes/{hid}/scores` actually
 * returns, which is narrower than it first looks: `tied_participants` is
 * populated *only* while a tie is unresolved, and a supplied `closest_to_pin`
 * naming a tied player always decides the hole. So there is no response meaning
 * "your pin answer failed to separate them" — the group reaches longest drive by
 * declining the pin question, which is why `Asked` exists.
 */

import { describe, expect, it } from 'vitest';

import { NOTHING_ASKED, nextPrompt, strokesFrom, type Asked } from './cascade';
import type { HoleResult } from '../../lib/types';

const A = 'aaaaaaaa-0000-0000-0000-000000000001';
const B = 'bbbbbbbb-0000-0000-0000-000000000002';
const C = 'cccccccc-0000-0000-0000-000000000003';

const PIN_DECLINED: Asked = { closestToPin: true, longestDrive: false };
const BOTH_DECLINED: Asked = { closestToPin: true, longestDrive: true };

function result(over: Partial<HoleResult>): HoleResult {
  return {
    hole_id: 'hole-1',
    winner_participant_id: null,
    decided_by: 'no_winner',
    closest_to_pin_participant_id: null,
    longest_drive_participant_id: null,
    scores: [
      { participant_id: A, strokes: 4, points: 0 },
      { participant_id: B, strokes: 4, points: 0 },
      { participant_id: C, strokes: 5, points: 0 },
    ],
    tied_participants: [],
    created_at: '',
    updated_at: '',
    ...over,
  };
}

describe('an outright winner', () => {
  it('settles immediately, with nothing to ask', () => {
    const hole = result({
      winner_participant_id: A,
      decided_by: 'strokes',
      scores: [
        { participant_id: A, strokes: 3, points: 1 },
        { participant_id: B, strokes: 5, points: 0 },
        { participant_id: C, strokes: 4, points: 0 },
      ],
    });

    expect(nextPrompt(hole, NOTHING_ASKED)).toEqual({ kind: 'settled', result: hole });
  });
});

describe('a tie on strokes', () => {
  it('asks closest to the pin, of the tied players only', () => {
    // C played the hole too and is irrelevant: ADR-007 contests the tie-break
    // among the tied players alone, and naming anyone else is a 422.
    const prompt = nextPrompt(result({ tied_participants: [A, B] }), NOTHING_ASKED);

    expect(prompt).toEqual({ kind: 'ask_closest_to_pin', candidates: [A, B] });
    expect(prompt).not.toMatchObject({ candidates: expect.arrayContaining([C]) });
  });

  it('settles once a pin answer decides it', () => {
    const hole = result({
      winner_participant_id: B,
      decided_by: 'closest_to_pin',
      closest_to_pin_participant_id: B,
      tied_participants: [],
    });

    expect(nextPrompt(hole, PIN_DECLINED)).toMatchObject({ kind: 'settled' });
  });

  it('moves to longest drive once the pin question is declined', () => {
    // "None of us reached the green." Nothing was sent, so the response is
    // unchanged — the progress is the caller's to remember.
    const hole = result({ tied_participants: [A, B] });

    expect(nextPrompt(hole, PIN_DECLINED)).toEqual({
      kind: 'ask_longest_drive',
      candidates: [A, B],
    });
  });

  it('treats a three-way tie no differently — the level ignores how many', () => {
    const hole = result({
      tied_participants: [A, B, C],
      scores: [
        { participant_id: A, strokes: 4, points: 0 },
        { participant_id: B, strokes: 4, points: 0 },
        { participant_id: C, strokes: 4, points: 0 },
      ],
    });

    expect(nextPrompt(hole, NOTHING_ASKED)).toEqual({
      kind: 'ask_closest_to_pin',
      candidates: [A, B, C],
    });
  });

  it('settles once a longest-drive answer decides it', () => {
    const hole = result({
      winner_participant_id: A,
      decided_by: 'longest_drive',
      longest_drive_participant_id: A,
      tied_participants: [],
    });

    expect(nextPrompt(hole, BOTH_DECLINED)).toMatchObject({ kind: 'settled' });
  });
});

describe('nobody wins', () => {
  it('stops asking once both questions are declined', () => {
    // Typically nobody found the fairway. The hole is already stored unwon —
    // holes are never halved — so there is nothing further to submit.
    const hole = result({ tied_participants: [A, B] });

    expect(nextPrompt(hole, BOTH_DECLINED)).toEqual({ kind: 'nobody_wins', candidates: [A, B] });
  });

  it('does not skip the questions just because the hole reads as unwon', () => {
    // A first submission of tied strokes comes back `no_winner` with nobody yet
    // asked. Announcing "nobody wins" here would skip the two questions that
    // usually settle it — and ADR-007 says an unwon hole should be uncommon.
    const hole = result({ decided_by: 'no_winner', tied_participants: [A, B] });

    expect(nextPrompt(hole, NOTHING_ASKED)).toMatchObject({ kind: 'ask_closest_to_pin' });
  });
});

describe('re-submitting', () => {
  it('rebuilds the strokes map, since an answer re-posts the whole hole', () => {
    // There is no separate tie-break endpoint: the same upsert carries a
    // correction and a late answer alike (ADR-009).
    expect(strokesFrom(result({}))).toEqual({ [A]: 4, [B]: 4, [C]: 5 });
  });
});
