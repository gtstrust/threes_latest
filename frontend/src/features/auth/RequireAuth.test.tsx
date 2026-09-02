/**
 * The gate has three states, not two, and the third is the one that bites.
 *
 * "Signed in" does not mean "ready": a verified Supabase token does not imply a
 * `players` row, and until `POST /players` succeeds every profile route answers
 * 404. Rendering the app in between shows a screen that silently cannot load
 * anything, which reads as a broken app rather than as a slow one.
 */

import { render, screen } from '@testing-library/react';
import type { Session } from '@supabase/supabase-js';
import { describe, expect, it, vi } from 'vitest';

import { RequireAuth } from './RequireAuth';
import { SessionContext, type SessionState } from './session-context';
import type { Player } from '../../lib/types';

vi.mock('../../lib/supabase', () => ({
  sendMagicLink: vi.fn(),
  signOut: vi.fn(),
  getAccessToken: vi.fn(),
  supabase: {},
}));

const PLAYER: Player = {
  id: 'p1',
  email: 'kim@example.com',
  display_name: 'Kim',
  created_at: '',
  updated_at: '',
};

function renderGate(state: Partial<SessionState>) {
  const value: SessionState = {
    session: null,
    player: null,
    loading: false,
    error: null,
    authError: null,
    retryProfile: vi.fn(),
    ...state,
  };
  return render(
    <SessionContext.Provider value={value}>
      <RequireAuth>
        <p>the app</p>
      </RequireAuth>
    </SessionContext.Provider>,
  );
}

const SIGNED_IN = { access_token: 't' } as Session;

describe('RequireAuth', () => {
  it('waits rather than bouncing a signed-in user to login', async () => {
    // The session arrives asynchronously. Treating "not yet known" as "signed
    // out" would flash the login screen at someone who is already signed in.
    renderGate({ loading: true, session: SIGNED_IN });

    expect(screen.getByText('Loading…')).toBeInTheDocument();
    expect(screen.queryByText('the app')).not.toBeInTheDocument();
  });

  it('asks for a magic link when signed out', () => {
    renderGate({ session: null });

    expect(screen.getByRole('button', { name: /send me a link/i })).toBeInTheDocument();
  });

  it('holds the app back until the profile exists', () => {
    renderGate({ session: SIGNED_IN, player: null });

    expect(screen.getByText(/setting up your profile/i)).toBeInTheDocument();
    expect(screen.queryByText('the app')).not.toBeInTheDocument();
  });

  it('offers a retry, not a sign-out, when provisioning fails', () => {
    // The session is usually fine and the server is the unreachable thing —
    // a 503 means the backend could not verify a good token. Signing the user
    // out would not fix it and would lose their place.
    renderGate({ session: SIGNED_IN, error: 'Could not reach Supabase' });

    expect(screen.getByRole('alert')).toHaveTextContent('Could not reach Supabase');
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /sign out/i })).not.toBeInTheDocument();
  });

  it('renders the app once signed in and provisioned', () => {
    renderGate({ session: SIGNED_IN, player: PLAYER });

    expect(screen.getByText('the app')).toBeInTheDocument();
  });
});
