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
import userEvent from '@testing-library/user-event';
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
const { NewFunRoundPage } = await import('./fun-rounds/NewFunRoundPage');
const { ApiError } = await import('../lib/api');
const { JoinPage } = await import('./join/JoinPage');
const { StatsPage } = await import('./stats/StatsPage');
const { TournamentSettingsPage } = await import('./tournaments/TournamentSettingsPage');
const { ScorecardPage } = await import('./scoring/ScorecardPage');
const { SessionContext } = await import('./auth/session-context');

const PLAYER_ID = 'player-kim';
const T = 'tournament-1';
const CODE = 'THR-8K2QF';
const FR = 'fun-round-1';
/** A round the signed-in player was sent the link to but is not yet in. */
const STRANGERS = 'fun-round-2';

const TOURNAMENT = {
  id: T,
  name: 'Acme Corporate Day',
  organiser_id: PLAYER_ID,
  join_code: CODE,
  max_players: null,
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
      join_code: 'THR-QQ44M',
      course_id: 'course-1',
      hole_numbers: [4, 5, 6],
      status: 'lobby',
      created_at: '',
      updated_at: '',
    },
  ],
  [`/fun-rounds/${FR}`]: {
    id: FR,
    name: 'Saturday nine',
    host_id: PLAYER_ID,
    join_code: 'THR-QQ44M',
    course_id: 'course-1',
    hole_numbers: [4, 5, 6],
    status: 'lobby',
    created_at: '',
    updated_at: '',
    participants: [
      {
        id: 'fp-kim',
        tournament_id: FR,
        player_id: PLAYER_ID,
        display_name: 'Kim',
        is_virtual: false,
      },
    ],
    round: null,
  },
  [`/fun-rounds/${STRANGERS}/preview`]: {
    id: STRANGERS,
    name: 'Sunday hit',
    host_name: 'Alex',
    player_count: 2,
    is_full: false,
    status: 'lobby',
  },
  [`/join/${CODE}`]: {
    kind: 'tournament',
    id: T,
    name: 'Acme Corporate Day',
    host_name: 'Kim',
    player_count: 2,
    can_join: true,
    status: 'REGISTRATION_OPEN',
  },
  '/players/me/stats': {
    career: {
      events_played: 3,
      holes_played: 9,
      holes_won: 4,
      total_strokes: 38,
      win_rate: 0.444,
      average_strokes: 4.22,
    },
    history: [
      {
        tournament_id: T,
        name: 'Acme Corporate Day',
        kind: 'TOURNAMENT',
        status: 'ROUND_IN_PROGRESS',
        played_at: '2026-08-01T00:00:00Z',
        position: 2,
        points: 1,
        total_strokes: 13,
        holes_played: 3,
      },
      // In it, not played yet — listed without a placing it hasn't earned.
      {
        tournament_id: FR,
        name: 'Saturday nine',
        kind: 'FUN_ROUND',
        status: 'REGISTRATION_OPEN',
        played_at: '2026-08-02T00:00:00Z',
        position: null,
        points: 0,
        total_strokes: 0,
        holes_played: 0,
      },
    ],
  },
  '/players/me/stats/courses': [
    {
      course_id: 'course-1',
      course_name: 'Royal Melbourne',
      rounds_played: 2,
      holes_played: 6,
      holes_won: 3,
      average_strokes: 4.17,
      holes: [
        {
          hole_number: 1,
          times_played: 2,
          holes_won: 2,
          best_strokes: 3,
          average_strokes: 3.5,
        },
        {
          hole_number: 2,
          times_played: 2,
          holes_won: 1,
          best_strokes: 4,
          average_strokes: 4.5,
        },
      ],
    },
  ],
  '/groups/group-1': {
    id: 'group-1',
    round_id: 'round-1',
    group_number: 1,
    members: [{ participant_id: 'p-kim' }, { participant_id: 'p-dave' }],
    holes: [{ hole_id: 'h1', sequence: 1 }],
  },
  '/groups/group-1/scores': {
    group_id: 'group-1',
    holes: [
      {
        hole_id: 'h1',
        // Nobody won it: the strokes tied and no tie-break separated them. A
        // real outcome (ADR-007), and the card has to say so rather than
        // showing a blank that reads as missing data.
        winner_participant_id: null,
        decided_by: 'no_winner',
        closest_to_pin_participant_id: null,
        longest_drive_participant_id: null,
        scores: [
          { participant_id: 'p-kim', strokes: 5, points: 0 },
          { participant_id: 'p-dave', strokes: 5, points: 0 },
        ],
        tied_participants: [],
        created_at: '',
        updated_at: '',
      },
    ],
  },
  '/courses': [
    { id: 'course-1', name: 'Royal Melbourne', created_by: PLAYER_ID, hole_count: 9 },
    // Created by this player and unplayable, which is the pair the picker has to
    // tell apart: they can fix this one, so it must offer them the way to.
    { id: 'course-2', name: 'Empty Links', created_by: PLAYER_ID, hole_count: 0 },
  ],
  '/courses/course-1': {
    id: 'course-1',
    name: 'Royal Melbourne',
    created_by: PLAYER_ID,
    // Nine holes, so the course offers three loops to choose between. The first
    // one is what the group card below plays.
    holes: Array.from({ length: 9 }, (_, index) => ({
      id: index === 0 ? 'h1' : `h${index + 1}`,
      course_id: 'course-1',
      hole_number: index + 1,
      par: null,
      stroke_index: null,
    })),
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
    player: {
      id: PLAYER_ID,
      email: 'kim@example.com',
      display_name: 'Kim',
      created_at: '',
      updated_at: '',
    },
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
    expect(await screen.findByRole('option', { name: /Royal Melbourne/ })).toBeInTheDocument();
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
    // A fun round is invited by the same short code as a tournament now, not
    // by its UUID — everyone in the round holds it, so any of them can pull a
    // fourth in.
    expect(screen.getByText('THR-QQ44M')).toBeInTheDocument();
    expect(await screen.findByText('Kim')).toBeInTheDocument();
    // Host, course set, so the round can be started.
    expect(screen.getByRole('button', { name: /start the round/i })).toBeInTheDocument();
  });

  it('an invite link you are not in yet offers a way in, not an error', async () => {
    // The 403 is how a mate arrives: they tapped the shared link. Showing them
    // the refusal instead of the invitation is the bug this covers.
    get.mockImplementation((path: string) => {
      if (path === `/fun-rounds/${STRANGERS}`)
        return Promise.reject(new ApiError(403, "You're not in this round yet — join it first"));
      return path in ROUTES
        ? Promise.resolve(ROUTES[path])
        : Promise.reject(new Error(`unexpected GET ${path}`));
    });

    show(<FunRoundPage funRoundId={STRANGERS} />);

    expect(await screen.findByText(/you.re invited/i)).toBeInTheDocument();
    expect(screen.getByText(/Alex is playing a fun round/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /i'm in/i })).toBeInTheDocument();
    // The field itself is not on an invite — you learn who is playing by joining.
    expect(screen.queryByText('Kim')).not.toBeInTheDocument();
  });

  it('the lobby says which three holes are being played', async () => {
    show(<FunRoundPage funRoundId={FR} />);

    expect(await screen.findByText(/Playing holes 4, 5, 6/)).toBeInTheDocument();
  });

  it('the course list says how many holes each course has', async () => {
    show(<NewFunRoundPage />);

    expect(
      await screen.findByRole('option', { name: /Royal Melbourne — 9 holes/ }),
    ).toBeInTheDocument();
    // The unplayable one is listed rather than hidden — it is the one worth
    // seeing, since whoever created it can fix it right here.
    expect(screen.getByRole('option', { name: /Empty Links — no holes/ })).toBeInTheDocument();
  });

  it('offers to fill in the holes of a course you created but never set up', async () => {
    const user = userEvent.setup();
    show(<NewFunRoundPage />);

    await user.selectOptions(await screen.findByLabelText(/course/i), 'course-2');

    expect(await screen.findByText(/has no holes entered yet/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/holes on the course/i)).toBeInTheDocument();
  });

  it('lets the host pick which loop to play once the course has more than three holes', async () => {
    const user = userEvent.setup();
    show(<NewFunRoundPage />);

    await user.selectOptions(await screen.findByLabelText(/course/i), 'course-1');

    const loop = await screen.findByLabelText(/which three holes/i);
    expect(loop).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Holes 7, 8, 9' })).toBeInTheDocument();
  });

  it('a join code shows what you were invited to, and a way in', async () => {
    show(<JoinPage code={CODE} />);

    expect(await screen.findByText(/you.re invited/i)).toBeInTheDocument();
    expect(screen.getByText(/Kim is running this event/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /i'm in/i })).toBeInTheDocument();
    // An invitation names the event, not its field.
    expect(screen.queryByText('Dave')).not.toBeInTheDocument();
  });

  it('a closed invitation explains itself instead of offering the button', async () => {
    get.mockImplementation((path: string) =>
      path === `/join/${CODE}`
        ? Promise.resolve({ ...(ROUTES[`/join/${CODE}`] as object), can_join: false })
        : path in ROUTES
          ? Promise.resolve(ROUTES[path])
          : Promise.reject(new Error(`unexpected GET ${path}`)),
    );

    show(<JoinPage code={CODE} />);

    expect(await screen.findByText(/joining has closed/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /i'm in/i })).not.toBeInTheDocument();
  });

  it('the organiser gets the join code and a QR to hand out', async () => {
    // ROUND_IN_PROGRESS is past the point of inviting, so use an event still open.
    get.mockImplementation((path: string) =>
      path === `/tournaments/${T}`
        ? Promise.resolve({ ...TOURNAMENT, status: 'REGISTRATION_OPEN' })
        : path in ROUTES
          ? Promise.resolve(ROUTES[path])
          : Promise.reject(new Error(`unexpected GET ${path}`)),
    );

    show(<TournamentPage tournamentId={T} />);

    expect(await screen.findByText(CODE)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: new RegExp(CODE) })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /copy join link/i })).toBeInTheDocument();
  });

  it('a tournament you are not in points you at the join link, not the guard', async () => {
    get.mockImplementation((path: string) => {
      if (path === `/tournaments/${T}`)
        return Promise.reject(
          new ApiError(403, 'Only the organiser and players in this tournament can view it'),
        );
      return path in ROUTES
        ? Promise.resolve(ROUTES[path])
        : Promise.reject(new Error(`unexpected GET ${path}`));
    });

    show(<TournamentPage tournamentId={T} />);

    expect(await screen.findByText(/you.re not in this event/i)).toBeInTheDocument();
    expect(screen.getByText(/ask the organiser for the join link/i)).toBeInTheDocument();
  });

  it('shows the field against its cap, and says so when it is full', async () => {
    get.mockImplementation((path: string) =>
      path === `/tournaments/${T}`
        ? Promise.resolve({ ...TOURNAMENT, status: 'REGISTRATION_OPEN', max_players: 2 })
        : path in ROUTES
          ? Promise.resolve(ROUTES[path])
          : Promise.reject(new Error(`unexpected GET ${path}`)),
    );

    show(<TournamentPage tournamentId={T} />);

    // Two participants in the fixture, cap of two.
    expect(await screen.findByText(/The field \(2 of 2\)/)).toBeInTheDocument();
    // The cap is edited on the settings screen now — one place, not two.
    expect(screen.getByRole('link', { name: /event settings/i })).toBeInTheDocument();
  });

  it('a full event explains itself rather than offering a join button', async () => {
    get.mockImplementation((path: string) => {
      if (path === `/tournaments/${T}`)
        return Promise.resolve({
          ...TOURNAMENT,
          organiser_id: 'someone-else',
          join_code: null,
          status: 'REGISTRATION_OPEN',
          max_players: 2,
        });
      if (path === `/tournaments/${T}/participants`)
        return Promise.resolve([
          { id: 'p-a', tournament_id: T, player_id: 'a', display_name: 'A', is_virtual: false },
          { id: 'p-b', tournament_id: T, player_id: 'b', display_name: 'B', is_virtual: false },
        ]);
      return path in ROUTES
        ? Promise.resolve(ROUTES[path])
        : Promise.reject(new Error(`unexpected GET ${path}`));
    });

    show(<TournamentPage tournamentId={T} />);

    expect(await screen.findByText(/this event is full/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /i'm playing/i })).not.toBeInTheDocument();
  });

  it('the organiser can remind the field while it can still change', async () => {
    get.mockImplementation((path: string) =>
      path === `/tournaments/${T}`
        ? Promise.resolve({ ...TOURNAMENT, status: 'REGISTRATION_OPEN' })
        : path in ROUTES
          ? Promise.resolve(ROUTES[path])
          : Promise.reject(new Error(`unexpected GET ${path}`)),
    );

    show(<TournamentPage tournamentId={T} />);

    expect(await screen.findByText('Remind the field')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send a reminder/i })).toBeInTheDocument();
    // Said up front, because a field of hand-added players has no addresses and
    // an organiser should not discover that from a count of zero.
    expect(screen.getByText(/no address to write to/i)).toBeInTheDocument();
  });

  it('does not offer a reminder once the round is under way', async () => {
    // The fixture is ROUND_IN_PROGRESS: they are on the course.
    show(<TournamentPage tournamentId={T} />);

    await screen.findByText('Acme Corporate Day');
    expect(screen.queryByText('Remind the field')).not.toBeInTheDocument();
  });

  it('your record shows career figures and the rounds behind them', async () => {
    show(<StatsPage />);

    expect(await screen.findByText('Career')).toBeInTheDocument();
    expect(screen.getByText('Round by round')).toBeInTheDocument();
    // Rounded server-side, shown as a share because 0.444 reads worse.
    expect(screen.getByText('44%')).toBeInTheDocument();
    expect(screen.getByText('4.22')).toBeInTheDocument();
    expect(screen.getByText('Acme Corporate Day')).toBeInTheDocument();
    expect(screen.getByText(/2nd/)).toBeInTheDocument();
  });

  it('an event you have not played yet is listed without a placing', async () => {
    show(<StatsPage />);

    expect(await screen.findByText('Saturday nine')).toBeInTheDocument();
    expect(screen.getByText(/not played yet/i)).toBeInTheDocument();
  });

  it('your record breaks down by course and by hole', async () => {
    show(<StatsPage />);

    expect(await screen.findByText('By course')).toBeInTheDocument();
    // The visit count leads, because a single round's "average" is just that
    // round and the number should not read as more than it is.
    expect(screen.getByText(/2 rounds/)).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Best' })).toBeInTheDocument();
    expect(screen.getByText('3.50')).toBeInTheDocument();
    expect(screen.getByText('2/2')).toBeInTheDocument();
  });

  it('event settings carries the date the reminder sweep depends on', async () => {
    get.mockImplementation((path: string) =>
      path === `/tournaments/${T}`
        ? Promise.resolve({
            ...TOURNAMENT,
            status: 'REGISTRATION_OPEN',
            scheduled_at: '2026-09-12T08:30:00+00:00',
          })
        : path in ROUTES
          ? Promise.resolve(ROUTES[path])
          : Promise.reject(new Error(`unexpected GET ${path}`)),
    );

    show(<TournamentSettingsPage tournamentId={T} />);

    const when = await screen.findByLabelText(/date and tee time/i);
    // Populated from the stored instant, not blank — the field has to show what
    // is already set or an organiser will overwrite it with nothing.
    expect((when as HTMLInputElement).value).toMatch(/^2026-09-12T/);
    expect(screen.getByLabelText(/maximum players/i)).toBeInTheDocument();
    expect(screen.getByText(/without a date, no reminder goes out/i)).toBeInTheDocument();
  });

  it('the scorecard says a halved hole was halved', async () => {
    show(<ScorecardPage groupId="group-1" />);

    expect(await screen.findByText(/how each hole went/i)).toBeInTheDocument();
    // Not a blank, not an error — "nobody won it" is the outcome.
    expect(screen.getByText(/nobody won it/i)).toBeInTheDocument();
    expect(screen.getAllByText('5').length).toBeGreaterThan(0);
  });

  it('your profile offers a display name, since the fallback is your email', async () => {
    show(<StatsPage />);

    expect(await screen.findByLabelText(/display name/i)).toBeInTheDocument();
    expect(screen.getByText(/your email address shows instead/i)).toBeInTheDocument();
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
