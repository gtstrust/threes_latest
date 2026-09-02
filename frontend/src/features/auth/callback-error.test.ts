/**
 * The failing half of the round trip. These pin two things the app cannot see
 * for itself: that a dead link is reported at all, and that reading it does not
 * disturb anything else on the URL.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

function visit(url: string) {
  window.history.replaceState({}, '', url);
}

/**
 * A fresh module per case. The real one answers once per page load and remembers,
 * which is what makes it safe to call during render — so a test that imported it
 * at the top would get the first case's answer for every case after it.
 */
async function takeCallbackError(): Promise<string | null> {
  vi.resetModules();
  return (await import('./callback-error')).takeCallbackError();
}

describe('takeCallbackError', () => {
  beforeEach(() => visit('/'));

  it('says nothing on an ordinary page load', async () => {
    expect(await takeCallbackError()).toBeNull();
  });

  it('says nothing on a successful callback', async () => {
    visit('/#access_token=abc&refresh_token=def&token_type=bearer');
    expect(await takeCallbackError()).toBeNull();
    // Left for supabase-js, which is what consumes it.
    expect(window.location.hash).toContain('access_token=abc');
  });

  it('explains an expired link in words that name the fix', async () => {
    visit('/#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid');
    expect(await takeCallbackError()).toBe('That sign-in link has expired. Send yourself a new one below.');
  });

  it('explains a link that has already been used', async () => {
    visit('/#error=access_denied');
    expect(await takeCallbackError()).toBe(
      'That sign-in link has already been used. Send yourself a new one below.',
    );
  });

  it("falls back to Supabase's own wording for a code it does not know", async () => {
    visit('/#error=server_error&error_code=unexpected_failure&error_description=Something+broke');
    expect(await takeCallbackError()).toBe('Something broke');
  });

  it('still reports an error with no description at all', async () => {
    visit('/#error_code=some_new_code');
    expect(await takeCallbackError()).toBe(
      'That sign-in link did not work. Send yourself a new one below.',
    );
  });

  it('reads the query string too, since Supabase returns errors in both', async () => {
    visit('/?error=access_denied&error_code=otp_expired');
    expect(await takeCallbackError()).toBe('That sign-in link has expired. Send yourself a new one below.');
  });

  it('takes the error off the URL, so a refresh does not resurrect it', async () => {
    visit('/#error=access_denied&error_code=otp_expired');
    expect(await takeCallbackError()).not.toBeNull();
    expect(window.location.hash).toBe('');
    expect(await takeCallbackError()).toBeNull();
  });

  it('leaves the path and any unrelated parameters alone', async () => {
    // A dead link on a QR join: the code in the path is the whole point of the
    // page they were trying to reach, and clearing the error must not cost it.
    visit('/join/THR-8K2QF?ref=MATE-2QF8K#error=access_denied&error_code=otp_expired');
    expect(await takeCallbackError()).not.toBeNull();
    expect(window.location.pathname).toBe('/join/THR-8K2QF');
    expect(window.location.search).toBe('?ref=MATE-2QF8K');
  });
});
