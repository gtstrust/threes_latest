import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { RequireAuth } from './features/auth/RequireAuth';
import { SessionProvider } from './features/auth/session';
import { HomePage } from './features/tournaments/HomePage';
import { NewTournamentPage } from './features/tournaments/NewTournamentPage';
import { TournamentPage } from './features/tournaments/TournamentPage';
import { LeaderboardPage } from './features/leaderboard/LeaderboardPage';
import { ScorePage } from './features/scoring/ScorePage';
import { NewFunRoundPage } from './features/fun-rounds/NewFunRoundPage';
import { FunRoundPage } from './features/fun-rounds/FunRoundPage';
import { FunRoundLeaderboardPage } from './features/fun-rounds/FunRoundLeaderboardPage';

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

function FunRoundRoute() {
  const { id } = useParams();
  return id ? <FunRoundPage funRoundId={id} /> : <Navigate to="/" replace />;
}

function FunRoundLeaderboardRoute() {
  const { id } = useParams();
  return id ? <FunRoundLeaderboardPage funRoundId={id} /> : <Navigate to="/" replace />;
}

function FunRoundScoreRoute() {
  const { id, groupId } = useParams();
  return id && groupId ? (
    <ScorePage groupId={groupId} backTo={{ to: `/r/${id}`, label: 'Fun round' }} />
  ) : (
    <Navigate to="/" replace />
  );
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
              {/* Fun rounds — casual, self-run. Short paths, shared by text. */}
              <Route path="/rounds/new" element={<NewFunRoundPage />} />
              <Route path="/r/:id" element={<FunRoundRoute />} />
              <Route path="/r/:id/leaderboard" element={<FunRoundLeaderboardRoute />} />
              <Route path="/r/:id/g/:groupId" element={<FunRoundScoreRoute />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </RequireAuth>
        </SessionProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
