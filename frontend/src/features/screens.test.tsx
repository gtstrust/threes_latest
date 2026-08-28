/**
 * Every screen renders, with data shaped the way the API really shapes it.
 *
 * Not a substitute for clicking through, but it catches the class of bug that
 * shows a player a white screen on a tee box — a bad destructure, a missing
 * provider, a route that never resolves. Cheap, and the failure it prevents is
 * the one there is no recovering from mid-round.
 *
 * The fixtures below match responses captured from a running backend.
 */

import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import type { SessionState } from './auth/session-context';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.fn();
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api');
  return {
    ...actual,
    api: { get: (p: string) => get(p), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  };
});
vi.mock('../lib/supabase', () => ({
  supabase: { channel: () => ({ on: () => ({ subscribe: () => ({}) }) }), removeChannel: vi.fn() },
  signOut: vi.fn(),
  sendMagicLink: vi.fn(),
  getAccessToken: vi.fn(),
}));
vi.mock('../lib/realtime', () => ({
  subscribeToTournament: () => () => {},
  tournamentTopic: (id: string) => `tournament:${id}`,
  LEADERBOARD_CHANGED: 'leaderboard_changed',
}));

const { HomePage } = await import('./tournaments/HomePage');
const { TournamentPage } = await import('./tournaments/TournamentPage');
const { NewTournamentPage } = await import('./tournaments/NewTournamentPage');
const { LeaderboardPage } = await import('./leaderboard/LeaderboardPage');
const { FunRoundPage } = await import('./fun-rounds/FunRoundPage');
const { SessionContext } = await import('./auth/session-context');

const PLAYER_ID = 'player-kim';
const T = 'tournament-1';
const FR = 'fun-round-1';

const TOURNAMENT = {
  id: T,
  name: 'Acme Corporate Day',
  organiser_id: PLAYER_ID,
  status: 'ROUND_IN_PROGRESS',
  format: 'ROUND_ROBIN',
  course_id: 'course-1',
  scheduled_at: null,
  created_at: '',
  updated_at: '',
};

const ROUTES: Record<string, unknown> = {
  '/tournaments': [TOURNAMENT],
  '/players/me/tournaments': [TOURNAMENT],
  [`/tournaments/${T}`]: TOURNAMENT,
  [`/tournaments/${T}/participants`]: [
    { id: 'p-kim', tournament_id: T, player_id: PLAYER_ID, display_name: 'Kim', is_virtual: false },
    { id: 'p-dave', tournament_id: T, player_id: null, display_name: 'Dave', is_virtual: true },
  ],
  [`/tournaments/${T}/rounds`]: [
    { id: 'round-1', tournament_id: T, round_number: 1, status: 'IN_PROGRESS' },
  ],
  '/rounds/round-1': {
    id: 'round-1',
    tournament_id: T,
    round_number: 1,
    status: 'IN_PROGRESS',
    groups: [
      {
        id: 'group-1',
        round_id: 'round-1',
        group_number: 1,
        members: [{ participant_id: 'p-kim' }, { participant_id: 'p-dave' }],
        holes: [{ hole_id: 'h1', sequence: 1 }],
      },
    ],
  },
  '/fun-rounds': [
    {
      id: FR,
      name: 'Saturday nine',
      host_id: PLAYER_ID,
      course_id: 'course-1',
      status: 'lobby',
      created_at: '',
      updated_at: '',
    },
  ],
  [`/fun-rounds/${FR}`]: {
    id: FR,
    name: 'Saturday nine',
    host_id: PLAYER_ID,
    course_id: 'course-1',
    status: 'lobby',
    created_at: '',
    updated_at: '',
    participants: [
      { id: 'fp-kim', tournament_id: FR, player_id: PLAYER_ID, display_name: 'Kim', is_virtual: false },
    ],
    round: null,
  },
  '/courses': [{ id: 'course-1', name: 'Royal Melbourne' }],
  '/courses/course-1': {
    id: 'course-1',
    name: 'Royal Melbourne',
    holes: [{ id: 'h1', course_id: 'course-1', hole_number: 1, par: null, stroke_index: null }],
  },
  [`/tournaments/${T}/leaderboard`]: {
    tournament_id: T,
    round_id: null,
    entries: [
      {
        position: 1,
        participant_id: 'p-kim',
        display_name: 'Kim',
        points: 2,
        total_strokes: 11,
        holes_played: 3,
      },
      // Level on points, split by strokes — and a player yet to score, who must
      // still be listed: a board missing half the field reads as a bug.
      {
        position: 2,
        participant_id: 'p-dave',
        display_name: 'Dave',
        points: 0,
        total_strokes: 0,
        holes_played: 0,
      },
    ],
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  get.mockImplementation((path: string) =>
    path in ROUTES
      ? Promise.resolve(ROUTES[path])
      : Promise.reject(new Error(`unexpected GET ${path}`)),
  );
});

function show(ui: ReactNode) {
  const session: SessionState = {
    session: { access_token: 't' } as never,
    player: { id: PLAYER_ID, email: 'kim@example.com', display_name: 'Kim', created_at: '', updated_at: '' },
    loading: false,
    error: null,
    retryProfile: vi.fn(),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SessionContext.Provider value={session}>{ui}</SessionContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('screens render', () => {
  it('home lists what you play and what you organise, separately', async () => {
    show(<HomePage />);

    expect(await screen.findByText('Playing in')).toBeInTheDocument();
    expect(screen.getByText('Organising')).toBeInTheDocument();
    // Both lists hold the same event — the organiser is playing too, which is
    // the normal case for a corporate day, not duplication.
    expect(await screen.findAllByText('Acme Corporate Day')).toHaveLength(2);
  });

  it('a tournament shows the field, the draw and the controls', async () => {
    show(<TournamentPage tournamentId={T} />);

    expect(await screen.findByText('Acme Corporate Day')).toBeInTheDocument();
    expect(await screen.findByText('Kim')).toBeInTheDocument();
    expect(screen.getByText(/no account/i)).toBeInTheDocument();
    expect(await screen.findByText(/Group 1/)).toBeInTheDocument();
  });

  it('never offers a status the API refuses', async () => {
    // ADR-008: the play statuses belong to the round endpoints. Offering them
    // here would produce a 409 the organiser cannot act on.
    show(<TournamentPage tournamentId={T} />);
    await screen.findByText('Acme Corporate Day');

    for (const forbidden of [/round in progress/i, /round complete/i]) {
      expect(screen.queryByRole('button', { name: forbidden })).not.toBeInTheDocument();
    }
    expect(await screen.findByRole('button', { name: /finish round 1/i })).toBeInTheDocument();
  });

  it('the setup form renders with the course list', async () => {
    show(<NewTournamentPage />);

    expect(await screen.findByLabelText(/tournament name/i)).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'Royal Melbourne' })).toBeInTheDocument();
  });

  it('home offers fun rounds alongside tournaments', async () => {
    show(<HomePage />);

    expect(await screen.findByText('Fun rounds')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /start a fun round/i })).toBeInTheDocument();
    expect(await screen.findByText('Saturday nine')).toBeInTheDocument();
  });

  it('a fun round lobby shows the field, an invite and a start control', async () => {
    show(<FunRoundPage funRoundId={FR} />);

    expect(await screen.findByText('Saturday nine')).toBeInTheDocument();
    expect(screen.getByText(/invite your mates/i)).toBeInTheDocument();
    expect(await screen.findByText('Kim')).toBeInTheDocument();
    // Host, course set, so the round can be started.
    expect(screen.getByRole('button', { name: /start the round/i })).toBeInTheDocument();
  });

  it('the leaderboard shows positions, points and who is still out', async () => {
    show(<LeaderboardPage tournamentId={T} />);

    const rows = await screen.findAllByRole('row');
    expect(rows).toHaveLength(3); // header + two players
    expect(await screen.findByText('Kim')).toBeInTheDocument();
    // Dave has scored nothing and is still listed, on zero holes.
    expect(screen.getByText('Dave')).toBeInTheDocument();
  });
});
