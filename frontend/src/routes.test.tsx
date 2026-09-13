/**
 * The guard, and the one route outside it.
 *
 * Every other test in this app renders a screen directly, which is the right
 * default — it keeps them fast and stops a routing change breaking forty
 * assertions about score entry. This file is the deliberate exception, because
 * the thing it checks cannot be seen from inside a screen: `RequireAuth` used to
 * sit *outside* `<Routes>` and gate the whole app, and `/how-it-works` needed it
 * to become a layout route with one sibling.
 *
 * That restructure has exactly two ways to go wrong, and both are silent. The
 * explainer falls back inside the guard, so the guest it was written for meets a
 * login screen instead. Or the guard stops covering something, and an event is
 * readable signed out. One test each.
 */

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: () => Promise.resolve({ data: { session: null } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
    },
  },
  signOut: vi.fn(),
  sendMagicLink: vi.fn(),
  signInWithPassword: vi.fn(),
  signUpWithPassword: vi.fn(),
  getAccessToken: vi.fn(),
}));

vi.mock('./lib/realtime', () => ({
  subscribeToTournament: () => () => {},
  tournamentTopic: (id: string) => `tournament:${id}`,
  LEADERBOARD_CHANGED: 'leaderboard_changed',
}));

const App = (await import('./App')).default;

describe('routing, signed out', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
  });

  it('shows the explainer without an account, which is the whole point of it', async () => {
    window.history.pushState({}, '', '/how-it-works');

    render(<App />);

    expect(await screen.findByText('Three holes, not eighteen')).toBeInTheDocument();
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument();
  });

  it('still asks everyone else to sign in', async () => {
    window.history.pushState({}, '', '/t/tournament-1');

    render(<App />);

    expect(await screen.findByLabelText('Email')).toBeInTheDocument();
  });

  it('keeps the invitation behind the guard, as it always was', async () => {
    window.history.pushState({}, '', '/join/THR-8K2QF');

    render(<App />);

    expect(await screen.findByLabelText('Email')).toBeInTheDocument();
  });
});
