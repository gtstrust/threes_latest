/**
 * The explainer is prose, so most of it cannot be tested. Two things can, and
 * both rot silently otherwise.
 *
 * A help panel links into the walkthrough by slug. Rename a step and the link
 * still compiles, still renders, and lands the reader on step one with no error
 * anywhere — which is exactly the sort of thing nobody notices until a guest on
 * a tee taps it. So the links are checked here rather than trusted.
 */

import { describe, expect, it } from 'vitest';

import { findStep, STEPS, stepsFor, TOPICS } from './content';

describe('the walkthrough', () => {
  it('has no duplicate slugs, since the slug is the URL', () => {
    const ids = STEPS.map((step) => step.id);

    expect(new Set(ids).size).toBe(ids.length);
  });

  it('covers both tracks', () => {
    expect(stepsFor('player').length).toBeGreaterThan(0);
    expect(stepsFor('organiser').length).toBeGreaterThan(0);
  });

  it('opens on the format, because that is what nobody arrives knowing', () => {
    expect(STEPS[0].id).toBe('format');
    expect(STEPS[0].track).toBe('player');
  });

  it('gives every step something to say', () => {
    for (const step of STEPS) {
      expect(step.title).not.toBe('');
      expect(step.body.length).toBeGreaterThan(0);
    }
  });
});

describe('findStep', () => {
  it('finds a step by slug and places it in its own track', () => {
    const { step, index, of } = findStep('ties');

    expect(step.title).toBe('If you tie, we ask');
    expect(of[index]).toBe(step);
    expect(of.every((each) => each.track === 'player')).toBe(true);
  });

  it('derives the track from the step, so an organiser slug needs no second param', () => {
    const { step, of } = findStep('draw');

    expect(step.track).toBe('organiser');
    expect(of.every((each) => each.track === 'organiser')).toBe(true);
  });

  it('falls back to the first step rather than failing', () => {
    // A stale link in somebody's messages should open the explainer, not break.
    expect(findStep('no-such-step').step.id).toBe('format');
    expect(findStep(null).step.id).toBe('format');
  });

  it('reports the position within the track, not within every step', () => {
    const { index, of } = findStep('setup');

    // `setup` is the first organiser step but the seventh overall.
    expect(index).toBe(0);
    expect(of.length).toBeLessThan(STEPS.length);
  });
});

describe('the screen help', () => {
  it('only ever links at a step that exists', () => {
    const ids = new Set(STEPS.map((step) => step.id));

    for (const [key, topic] of Object.entries(TOPICS)) {
      expect(ids, `${key} links at a missing step`).toContain(topic.step);
    }
  });

  it('gives every topic something to say', () => {
    for (const [key, topic] of Object.entries(TOPICS)) {
      expect(topic.title, key).not.toBe('');
      expect(topic.body.length, key).toBeGreaterThan(0);
    }
  });

  it('covers the screens that carry a panel', () => {
    // Kept in step by hand with the `topic=` props in `features/`. If a screen
    // is wired to a key that is not here, `HelpPanel` renders nothing at all —
    // silently, which is why the list is written down.
    for (const key of [
      'scoring',
      'card',
      'board',
      'your-group',
      'run-the-day',
      'invitation',
      'formats',
      'draw-settings',
      'fun-round',
      'handicaps',
    ]) {
      expect(TOPICS, key).toHaveProperty(key);
    }
  });
});
