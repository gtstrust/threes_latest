import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { RequireAuth } from './features/auth/RequireAuth';
import { SessionProvider } from './features/auth/session';
import { HomePage } from './features/tournaments/HomePage';
import { NewTournamentPage } from './features/tournaments/NewTournamentPage';
import { TournamentPage } from './features/tournaments/TournamentPage';
import { LeaderboardPage } from './features/leaderboard/LeaderboardPage';
import { ScorePage } from './features/scoring/ScorePage';

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

/**
 * Route params are `string | undefined` to the type system but cannot be missing
 * here — the path would not have matched. These wrappers do the narrowing once,
 * so no screen carries a `!` or an impossible branch.
 */
function TournamentRoute() {
  const { id } = useParams();
  return id ? <TournamentPage tournamentId={id} /> : <Navigate to="/" replace />;
}

function LeaderboardRoute() {
  const { id } = useParams();
  return id ? <LeaderboardPage tournamentId={id} /> : <Navigate to="/" replace />;
}

function ScoreRoute() {
  const { groupId } = useParams();
  return groupId ? <ScorePage groupId={groupId} /> : <Navigate to="/" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SessionProvider>
          <RequireAuth>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/new" element={<NewTournamentPage />} />
              {/* Short paths on purpose: these get shared by text message on the
                  day, and a long URL is a worse thing to read out loud. */}
              <Route path="/t/:id" element={<TournamentRoute />} />
              <Route path="/t/:id/leaderboard" element={<LeaderboardRoute />} />
              <Route path="/g/:groupId" element={<ScoreRoute />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </RequireAuth>
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
