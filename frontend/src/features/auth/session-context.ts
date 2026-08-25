/**
 * The session context and its hook, kept out of the provider's file.
 *
 * Not an arbitrary split: React Fast Refresh only re-renders a module cleanly
 * when it exports components alone, so a file exporting both `SessionProvider`
 * and `useSession` loses hot reload for the whole auth tree.
 */

import { createContext, useContext } from 'react';
import type { Session } from '@supabase/supabase-js';

import type { Player } from '../../lib/types';

export type SessionState = {
  session: Session | null;
  /**
   * The `players` row. Null until provisioning succeeds — which is a distinct
   * state from being signed out, because a verified token does not imply a row
   * exists. See `session.tsx`.
   */
  player: Player | null;
  /** True until the first auth check settles, so guards don't bounce a signed-in user. */
  loading: boolean;
  error: string | null;
  retryProfile: () => void;
};

export const SessionContext = createContext<SessionState | undefined>(undefined);

export function useSession(): SessionState {
  const context = useContext(SessionContext);
  if (!context) throw new Error('useSession must be used inside a SessionProvider');
  return context;
}
