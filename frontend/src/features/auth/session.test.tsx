/**
 * The provider that actually completes login, which until now had no test.
 *
 * The case that matters is the silent one: a magic link that has expired or been
 * used already comes back as an error on the URL, `supabase-js` throws it away
 * inside an internal `.catch()`, and before `callback-error.ts` the player landed
 * on the sign-in form with no idea why. A regression here is invisible in
 * production — nothing errors, nothing logs, people just cannot get in — so it is
 * worth pinning.
 */

import { StrictMode, type ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getSession, onAuthStateChange, post } = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../../lib/supabase', () => ({
  supabase: { auth: { getSession, onAuthStateChange } },
  sendMagicLink: vi.fn(),
  signOut: vi.fn(),
  getAccessToken: vi.fn(),
}));

vi.mock('../../lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../lib/api')>()),
  api: { post },
}));

function visit(url: string) {
  window.history.replaceState({}, '', url);
}

/**
 * A fresh module graph per case, and both modules imported after the same reset
 * so they share one context instance.
 *
 * `callback-error` answers once per page load and remembers — that memo is what
 * makes it safe to read during render. Importing at the top of the file would
 * hand every case after the first the first one's answer.
 */
async function renderApp(wrap: (ui: ReactNode) => ReactNode = (ui) => ui) {
  vi.resetModules();
  const { SessionProvider } = await import('./session');
  const { RequireAuth } = await import('./RequireAuth');
  return render(
    wrap(
      <SessionProvider>
        <RequireAuth>
          <p>Signed in</p>
        </RequireAuth>
      </SessionProvider>,
    ),
  );
}

const SESSION = { access_token: 'token', user: { id: 'u1' } };
const PLAYER = { id: 'u1', email: 'kim@example.com', display_name: 'Kim' };

beforeEach(() => {
  vi.clearAllMocks();
  visit('/');
  // Shape matters: session.tsx destructures `{ data: subscription }` and then
  // reaches through to `subscription.subscription.unsubscribe`.
  onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } });
  getSession.mockResolvedValue({ data: { session: null } });
  post.mockResolvedValue(PLAYER);
});

describe('SessionProvider', () => {
  it('provisions the profile once a session exists, then renders the app', async () => {
    getSession.mockResolvedValue({ data: { session: SESSION } });

    await renderApp();

    expect(await screen.findByText('Signed in')).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/players', {});
  });

  it('tells a player their link expired instead of silently showing the form again', async () => {
    visit('/#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid');

    await renderApp();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'That sign-in link has expired. Send yourself a new one below.',
    );
    // Still the sign-in screen — the message sits beside the form that fixes it.
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });

  it('keeps the message through StrictMode’s second pass', async () => {
    // The first pass takes the error off the URL, so the second finds nothing.
    // Assigning that nothing would wipe the message before anyone read it, and
    // the bug would only ever show in development.
    visit('/#error=access_denied&error_code=otp_expired');

    await renderApp((ui) => <StrictMode>{ui}</StrictMode>);

    expect(await screen.findByRole('alert')).toHaveTextContent('That sign-in link has expired.');
  });

  it('says nothing about links on an ordinary signed-out visit', async () => {
    await renderApp();

    await waitFor(() => expect(screen.getByLabelText('Email')).toBeInTheDocument());
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('offers a retry when the profile call fails rather than signing anyone out', async () => {
    getSession.mockResolvedValue({ data: { session: SESSION } });
    post.mockRejectedValue(new Error('boom'));

    await renderApp();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not reach the server. Check your connection.',
    );
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });
});
