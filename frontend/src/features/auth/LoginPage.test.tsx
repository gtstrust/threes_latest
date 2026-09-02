/**
 * What the magic link is asked to come back to.
 *
 * This string is one half of a contract whose other half lives in a dashboard:
 * Supabase only honours an `emailRedirectTo` that matches its redirect allow
 * list, and **silently substitutes the Site URL when it does not**. Nothing
 * fails — `signInWithOtp` returns success and the wrong link is emailed — so the
 * first sign of a mismatch is a player landing somewhere they did not start.
 *
 * It went wrong that way once already, with the allow list holding a bare origin
 * that could not match either value below. The allow list is now
 * `https://app.threes.golf/**`, and these tests pin the shape it was widened
 * for. Reducing this to `window.location.origin` would keep every other test
 * green while quietly breaking the case in the second one.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const sendMagicLink = vi.fn();
vi.mock('../../lib/supabase', () => ({
  sendMagicLink: (email: string, redirectTo: string) => sendMagicLink(email, redirectTo),
}));

const { LoginPage } = await import('./LoginPage');

/** jsdom serves the app from `http://localhost:3000`; only the path varies here. */
const ORIGIN = 'http://localhost:3000';

async function signIn(path: string) {
  window.history.pushState({}, '', path);
  render(<LoginPage />);
  await userEvent.type(screen.getByLabelText('Email'), 'kim@example.com');
  await userEvent.click(screen.getByRole('button', { name: /send me a link/i }));
}

beforeEach(() => {
  sendMagicLink.mockReset();
});

describe('requesting a magic link', () => {
  it('comes back to the login page it was requested from', async () => {
    await signIn('/');

    expect(sendMagicLink).toHaveBeenCalledWith('kim@example.com', `${ORIGIN}/`);
  });

  it('comes back to the join link a player scanned, not the home screen', async () => {
    // The reason the allow list needs `/**` rather than `/*`: two segments, and
    // this is the path most links are opened at — off a QR code at registration,
    // by somebody who has never loaded the site before.
    await signIn('/join/THR-8K2QF');

    expect(sendMagicLink).toHaveBeenCalledWith('kim@example.com', `${ORIGIN}/join/THR-8K2QF`);
  });

  it('tells the player when the link could not be sent', async () => {
    sendMagicLink.mockRejectedValueOnce(new Error('Email rate limit exceeded'));

    await signIn('/');

    expect(await screen.findByRole('alert')).toHaveTextContent('Email rate limit exceeded');
  });
});
