import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { RequireAuth } from './features/auth/RequireAuth';
import { SessionProvider } from './features/auth/session';
import { useSession } from './features/auth/session-context';
import { signOut } from './lib/supabase';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The leaderboard is invalidated by the realtime signal (ADR-010) rather
      // than by polling, so a short stale time is not what keeps it fresh.
      // Refetching on window focus is, though: a phone that has been in a pocket
      // for three holes should catch up the moment it comes out.
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

function Home() {
  const { player } = useSession();
  return (
    <main className="centred">
      <h1>Threes</h1>
      <p>
        Signed in as <strong>{player?.display_name ?? player?.email}</strong>
      </p>
      <p>Tournaments, scoring and the leaderboard land in the next slices.</p>
      <button type="button" onClick={() => void signOut()}>
        Sign out
      </button>
    </main>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionProvider>
          <Routes>
            <Route
              path="/"
              element={
                <RequireAuth>
                  <Home />
                </RequireAuth>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
