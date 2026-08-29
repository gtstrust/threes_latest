/**
 * The conversion that decides whether a reminder fires on the right day.
 *
 * Asserted as a round trip rather than against fixed strings: the machine
 * running these tests has its own timezone, and a test that only passes in
 * Australia is worse than no test. What must hold everywhere is that a wall
 * clock the organiser typed comes back as the same wall clock.
 */

import { describe, expect, it } from 'vitest';

import { readableWhen, toInstant, toLocalInput } from './when';

describe('tee times', () => {
  it('round-trips a wall clock through the wire and back', () => {
    const typed = '2026-09-12T08:30';

    const stored = toInstant(typed);
    expect(stored).toMatch(/Z$/); // an instant, not a naive string

    expect(toLocalInput(stored)).toBe(typed);
  });

  it('does not drift the hour', () => {
    // The failure this guards: converting via toISOString() on the way *out*
    // as well, which shifts by the offset and moves the tee time — and with it
    // the day the reminder is sent.
    for (const typed of ['2026-01-01T00:00', '2026-06-30T23:59', '2026-09-12T08:30']) {
      expect(toLocalInput(toInstant(typed))).toBe(typed);
    }
  });

  it('treats empty as no date, which is what keeps an event out of the sweep', () => {
    expect(toInstant('')).toBeNull();
    expect(toLocalInput(null)).toBe('');
    expect(readableWhen(null)).toBeNull();
  });

  it('refuses to invent a date from nonsense', () => {
    expect(toInstant('not a date')).toBeNull();
    expect(toLocalInput('not a date')).toBe('');
  });

  it('says a time the way somebody would read it out', () => {
    const said = readableWhen(toInstant('2026-09-12T08:30'));
    expect(said).toContain('12');
    expect(said).toContain('Sep');
    expect(said).toMatch(/8:30\s?am/i);
  });
});
