/**
 * The gate every authenticated route sits behind.
 *
 * Three states, not two. "Signed in" is not enough to render the app, because a
 * verified token without a `players` row makes every profile route 404 — so the
 * provisioning has to have succeeded too. Rendering children before it does
 * would show a screen that silently cannot load anything.
 */

import type { ReactNode } from 'react';

import { LoginPage } from './LoginPage';
import { useSession } from './session-context';

export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, player, loading, error, retryProfile } = useSession();

  if (loading) {
    return (
      <main className="centred">
        <p>Loading…</p>
      </main>
    );
  }

  if (!session) return <LoginPage />;

  if (error) {
    return (
      <main className="centred">
        <h1>Almost there</h1>
        {/* Deliberately not a sign-out prompt: the session is usually fine and the
            server is the thing that is unreachable. Sending people back through
            a magic link would not fix it and would lose their place. */}
        <p role="alert">{error}</p>
        <button type="button" onClick={retryProfile}>
          Try again
        </button>
      </main>
    );
  }

  if (!player) {
    return (
      <main className="centred">
        <p>Setting up your profile…</p>
      </main>
    );
  }

  return <>{children}</>;
}
