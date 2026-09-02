/**
 * Supabase, used for exactly two things: logging in, and being told to refetch.
 *
 * ADR-001 says the client does not query Supabase for data — every byte comes
 * from FastAPI, where the authorization guards live. That holds literally here:
 * this module exposes auth and a realtime channel, and nothing else. There is no
 * `.from('tournaments')` anywhere in this codebase, and there should never be —
 * the tables all carry deny-all row level security precisely so that a mistake
 * of that shape fails loudly instead of quietly returning nothing.
 */

import { createClient } from '@supabase/supabase-js';

import { env } from './env';

export const supabase = createClient(env.supabaseUrl, env.supabasePublishableKey, {
  auth: {
    // The magic link arrives as a fragment on the callback URL; this consumes it
    // and then the session persists to localStorage for subsequent loads.
    detectSessionInUrl: true,
    persistSession: true,
    autoRefreshToken: true,
    // Stated rather than inherited. This is the SDK's current default, and every
    // part of the app assumes it: the callback is read out of the fragment, and
    // there is no `exchangeCodeForSession` anywhere. The day that default flips
    // to PKCE, the link comes back as `?code=` instead, `_getSessionFromURL`
    // throws into an internal `.catch()` that only debug-logs, and login dies in
    // production with a green build and no error on screen. Naming it means an
    // SDK upgrade cannot change the flow without someone deciding to.
    flowType: 'implicit',
  },
});

/**
 * Send a magic link. Supabase creates the user if they are new, so there is no
 * separate sign-up — which is the point of the format: an organiser mails a link
 * and people are in.
 */
export async function sendMagicLink(email: string, redirectTo: string): Promise<void> {
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: redirectTo },
  });
  if (error) throw error;
}

/**
 * Sign in with a password — the way in that does not involve an inbox.
 *
 * A bypass, kept while Supabase's built-in sender rate-limits magic links to two
 * an hour. See `env.passwordLoginEnabled`, which hides it.
 */
export async function signInWithPassword(email: string, password: string): Promise<void> {
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
}

/**
 * Create an account with a password, signed in immediately.
 *
 * No `emailRedirectTo`, unlike `sendMagicLink`: the project has email
 * confirmations off, so `signUp` returns a session there and then and sends
 * nothing. Passing a redirect would describe a round trip that does not happen.
 *
 * **This does not put a password on an account that already exists.** Supabase
 * answers an already-registered address without setting one, so an account
 * created by magic link stays reachable only by magic link — a password has to be
 * set on it from the dashboard instead.
 */
export async function signUpWithPassword(email: string, password: string): Promise<void> {
  const { error } = await supabase.auth.signUp({ email, password });
  if (error) throw error;
}

export async function signOut(): Promise<void> {
  await supabase.auth.signOut();
}

/**
 * The current access token, or null when signed out.
 *
 * Read fresh on every request rather than captured once: the SDK rotates the
 * token in the background, and a copy taken at render time goes stale mid-round.
 */
export async function getAccessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
