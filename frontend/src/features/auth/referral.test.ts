/**
 * The referral code has to survive a magic-link round trip, which is the only
 * genuinely hard part of referrals on a passwordless app: the query string that
 * carried it is gone by the time there is a session to attribute.
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { captureReferral, takeReferral } from './referral';

function visit(url: string) {
  window.history.replaceState({}, '', url);
}

describe('referral capture', () => {
  beforeEach(() => {
    // jsdom here has no localStorage at all, which is exactly the condition the
    // module has to survive — this suite therefore exercises the in-memory
    // fallback, and the same assertions hold either way.
    window.localStorage?.clear();
    // Drain anything a previous test stashed, since the fallback is module state.
    takeReferral();
    visit('/');
  });

  it('stashes a code from the URL and takes it out of the address bar', () => {
    visit('/?ref=MATE-8K2QF');

    captureReferral();

    // Left in the URL, it would survive a refresh and follow a forwarded link,
    // carrying somebody else's attribution with it.
    expect(window.location.search).toBe('');
    expect(takeReferral()).toBe('MATE-8K2QF');
  });

  it('survives the round trip that loses the query string', () => {
    visit('/?ref=MATE-8K2QF');
    captureReferral();

    // What the magic link does: a different URL entirely, possibly a new tab.
    visit('/#access_token=abc');

    expect(takeReferral()).toBe('MATE-8K2QF');
  });

  it('is consumed once, so it cannot be offered again on a later sign-in', () => {
    visit('/?ref=MATE-8K2QF');
    captureReferral();

    expect(takeReferral()).toBe('MATE-8K2QF');
    expect(takeReferral()).toBeUndefined();
  });

  it('does nothing when there is no code, and leaves any stash alone', () => {
    visit('/?ref=MATE-EARLIER');
    captureReferral();

    visit('/');
    captureReferral();

    expect(takeReferral()).toBe('MATE-EARLIER');
  });

  it('does not break sign-in when the browser has no usable storage', () => {
    // The reason this module guards at all: it runs inside the sign-in path, so
    // a throw here would cost somebody their login to save a piece of analytics.
    visit('/?ref=MATE-8K2QF');

    expect(() => captureReferral()).not.toThrow();
    expect(takeReferral()).toBe('MATE-8K2QF');
  });

  it('keeps other query parameters', () => {
    visit('/?ref=MATE-8K2QF&utm_source=text');

    captureReferral();

    expect(window.location.search).toBe('?utm_source=text');
  });
});
