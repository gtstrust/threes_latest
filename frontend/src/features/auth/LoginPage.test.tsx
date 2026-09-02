/**
 * What the magic link is asked to come back to, and the password way in beside it.
 *
 * The redirect string is one half of a contract whose other half lives in a
 * dashboard: Supabase only honours an `emailRedirectTo` that matches its redirect
 * allow list, and **silently substitutes the Site URL when it does not**. Nothing
 * fails — `signInWithOtp` returns success and the wrong link is emailed — so the
 * first sign of a mismatch is a player landing somewhere they did not start.
 *
 * It went wrong that way once already, with the allow list holding a bare origin
 * that could not match either value below. The allow list is now
 * `https://app.threes.golf/**`, and these tests pin the shape it was widened
 * for. Reducing this to `window.location.origin` would keep every other test
 * green while quietly breaking the case in the second one.
 *
 * The password tests cover the bypass that exists because the link often never
 * arrives at all — two messages an hour from Supabase's built-in sender. It is
 * behind a flag, and the flag being honoured is itself worth a test: it is the
 * off switch for a thing that should not outlive the outage.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { sendMagicLink, signInWithPassword, signUpWithPassword, flags } = vi.hoisted(() => ({
  sendMagicLink: vi.fn(),
  signInWithPassword: vi.fn(),
  signUpWithPassword: vi.fn(),
  flags: { passwordLoginEnabled: true },
}));

vi.mock('../../lib/supabase', () => ({
  sendMagicLink,
  signInWithPassword,
  signUpWithPassword,
}));

// Mocked rather than left to ambient `VITE_*`, so the flag can be flipped per
// test and the suite does not depend on a `.env` existing.
vi.mock('../../lib/env', () => ({
  env: {
    get passwordLoginEnabled() {
      return flags.passwordLoginEnabled;
    },
  },
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

/** Open the disclosure and fill both fields, without submitting. */
async function openPasswordForm() {
  window.history.pushState({}, '', '/');
  render(<LoginPage />);
  await userEvent.click(screen.getByRole('button', { name: /use a password/i }));
  await userEvent.type(screen.getByLabelText('Email'), 'kim@example.com');
  await userEvent.type(screen.getByLabelText('Password'), 'not-a-real-one');
}

beforeEach(() => {
  vi.clearAllMocks();
  flags.passwordLoginEnabled = true;
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

describe('signing in with a password', () => {
  it('is offered but not in the way — the link stays the primary action', () => {
    render(<LoginPage />);

    expect(screen.getByRole('button', { name: /send me a link/i })).toBeInTheDocument();
    // Behind a disclosure, so the ordinary path is still the obvious one.
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /use a password/i })).toBeInTheDocument();
  });

  it('signs in with what was typed, without emailing anything', async () => {
    await openPasswordForm();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(signInWithPassword).toHaveBeenCalledWith('kim@example.com', 'not-a-real-one');
    expect(sendMagicLink).not.toHaveBeenCalled();
  });

  it('creates an account only when asked to, never by guessing', async () => {
    await openPasswordForm();
    await userEvent.click(screen.getByRole('button', { name: /create one/i }));
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));

    expect(signUpWithPassword).toHaveBeenCalledWith('kim@example.com', 'not-a-real-one');
    // A wrong password must not quietly become a second account.
    expect(signInWithPassword).not.toHaveBeenCalled();
  });

  it('says why a sign-in was refused', async () => {
    signInWithPassword.mockRejectedValueOnce(new Error('Invalid login credentials'));

    await openPasswordForm();
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid login credentials');
  });

  it('disappears entirely when the flag is off', async () => {
    // The off switch, for once SMTP is configured. Worth knowing it works before
    // it is needed, since the alternative is discovering it does not.
    flags.passwordLoginEnabled = false;

    render(<LoginPage />);

    expect(screen.queryByRole('button', { name: /use a password/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send me a link/i })).toBeInTheDocument();
  });
});
