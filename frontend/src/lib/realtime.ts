/**
 * The client half of ADR-010: being told the leaderboard moved.
 *
 * The server broadcasts a contentless ping on `tournament:{id}` after each hole
 * is scored. The **payload is deliberately empty of scores** — it says only that
 * something changed — and the correct response is to refetch the leaderboard
 * through FastAPI, where `require_can_view` decides what this caller may see.
 *
 * So: never read data out of the message. If a future payload tempts you to
 * render straight from it, that is the moment a second, unguarded read path
 * appears in the app, which is precisely what ADR-010 was written to prevent.
 */

import type { RealtimeChannel } from '@supabase/supabase-js';

import { supabase } from './supabase';
import type { LeaderboardChanged, UUID } from './types';

export const LEADERBOARD_CHANGED = 'leaderboard_changed';

/** The topic the backend broadcasts to. Must match `TOURNAMENT_TOPIC` server-side. */
export function tournamentTopic(tournamentId: UUID): string {
  return `tournament:${tournamentId}`;
}

/**
 * Subscribe to one tournament's signal.
 *
 * `onChanged` is called with the payload purely so a caller can scope an
 * invalidation to the round that moved; it carries nothing renderable.
 *
 * Returns an unsubscribe function — call it on unmount. Leaving channels open
 * across navigation is how you end up with a socket per screen visited and a
 * board that refetches once per stale subscription.
 */
export function subscribeToTournament(
  tournamentId: UUID,
  onChanged: (payload: LeaderboardChanged) => void,
): () => void {
  const channel: RealtimeChannel = supabase
    .channel(tournamentTopic(tournamentId))
    .on('broadcast', { event: LEADERBOARD_CHANGED }, (message) => {
      onChanged(message.payload as LeaderboardChanged);
    })
    .subscribe();

  return () => {
    void supabase.removeChannel(channel);
  };
}
