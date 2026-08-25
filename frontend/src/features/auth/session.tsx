/**
 * Who is signed in, and whether their profile exists yet.
 *
 * Those are two different questions, and conflating them is the first thing that
 * goes wrong against this API. A verified Supabase token proves identity but
 * does **not** imply a `players` row: `id` mirrors `auth.users.id`, but the row
 * is created lazily. `POST /players` is the idempotent "ensure my profile
 * exists" call, and until it succeeds every other `/players` route answers 404.
 *
 * So the provisioning happens here, once, on the way in — rather than being left
 * for each feature to remember.
 */

import { useEffect, useState, type ReactNode } from 'react';
import type { Session } from '@supabase/supabase-js';

import { api, ApiError } from '../../lib/api';
import { supabase } from '../../lib/supabase';
import type { Player } from '../../lib/types';
import { SessionContext, type SessionState } from './session-context';

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [player, setPlayer] = useState<Player | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setLoading(false);
    });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      if (!next) setPlayer(null);
      setLoading(false);
    });

    return () => {
      active = false;
      subscription.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    let active = true;

    void (async () => {
      try {
        // Idempotent: safe on every sign-in, and the only way the row ever appears.
        const profile = await api.post<Player>('/players', {});
        if (active) {
          setPlayer(profile);
          setError(null);
        }
      } catch (cause) {
        if (!active) return;
        // 503 means the backend could not reach Supabase to verify a token that
        // is probably fine. Signing the user out over someone else's outage
        // would be the wrong answer, so it is offered as a retry instead.
        const message =
          cause instanceof ApiError
            ? cause.detail
            : 'Could not reach the server. Check your connection.';
        setError(message);
      }
    })();

    return () => {
      active = false;
    };
  }, [session, attempt]);

  const value: SessionState = {
    session,
    player,
    loading,
    error,
    retryProfile: () => setAttempt((n) => n + 1),
  };

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
