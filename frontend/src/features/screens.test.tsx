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
// `patch` is spied on rather than anonymous because the settings screen is the
// only place a PATCH body is worth asserting on — it is where an event becomes
// fourballs and a shotgun, and getting that body wrong is silent.
const patch = vi.fn();
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api');
  return {
    ...actual,
    api: {
      get: (p: string) => get(p),
      patch: (p: string, body: unknown) => patch(p, body),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    },
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
const { ScorePage } = await import('./scoring/ScorePage');
const { SessionContext } = await import('./auth/session-context');
const { HowItWorksPage } = await import('./help/HowItWorksPage');

const PLAYER_ID = 'player-kim';
const T = 'tournament-1';
const CODE = 'THR-8K2QF';
const FR = 'fun-round-1';
/** A round the signed-in player was sent the link to but is not yet in. */
const STRANGERS = 'fun-round-2';

/**
 * The loop this group plays: holes 7, 8 and 9 of a nine-hole course.
 *
 * Deliberately not the first three. The draw is a shotgun start, so a group is
 * usually *not* on the 1st — and a fixture that starts at hole 1 makes the
 * course's own hole number and the position in the loop the same number, which
 * is exactly the confusion these screens have to keep apart.
 */
const LOOP = [
  { hole_id: 'h7', sequence: 1 },
  { hole_id: 'h8', sequence: 2 },
  { hole_id: 'h9', sequence: 3 },
];

const TOURNAMENT = {
  id: T,
  name: 'Acme Corporate Day',
  organiser_id: PLAYER_ID,
  join_code: CODE,
  max_players: null,
  status: 'ROUND_IN_PROGRESS',
  format: 'ROUND_ROBIN',
  group_size: 3,
  loop_style: 'BLOCKS',
  handicap_enabled: false,
  course_id: 'course-1',
  scheduled_at: null,
  created_at: '',
  updated_at: '',
};

const ROUTES: Record<string, unknown> = {
  // Two: one being played (promoted to the hero) and one still open (in the
  // list, where the role badge shows). Both organised by this player.
  '/tournaments': [
    TOURNAMENT,
    { ...TOURNAMENT, id: 'tournament-2', name: 'Q3 Client Day', status: 'REGISTRATION_OPEN' },
  ],
  '/players/me/tournaments': [TOURNAMENT],
  [`/tournaments/${T}`]: TOURNAMENT,
  [`/tournaments/${T}/participants`]: [
    {
      id: 'p-kim',
      tournament_id: T,
      player_id: PLAYER_ID,
      display_name: 'Kim',
      is_virtual: false,
      playing_handicap: null,
    },
    {
      id: 'p-dave',
      tournament_id: T,
      player_id: null,
      display_name: 'Dave',
      is_virtual: true,
      playing_handicap: null,
    },
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
        holes: LOOP,
        advancing_participant_id: null,
        advanced_by: null,
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
        rounds_survived: null,
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
        rounds_survived: null,
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
    holes: LOOP,
  },
  '/groups/group-1/scores': {
    group_id: 'group-1',
    holes: [
      {
        hole_id: 'h7',
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
        rounds_survived: null,
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
        rounds_survived: null,
      },
    ],
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  patch.mockResolvedValue(TOURNAMENT);
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
    authError: null,
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
  it('lists every event once, badged with which you are', async () => {
    show(<HomePage />);

    expect(await screen.findByText('Your events')).toBeInTheDocument();
    // The fixture has the same event in both /tournaments and
    // /players/me/tournaments — the organiser is playing too, which is the
    // normal case for a corporate day. It used to appear in two lists; now it
    // appears once, badged with the role that changes what the screen offers.
    expect(await screen.findAllByText('Acme Corporate Day')).toHaveLength(1);
    // The still-open event sits in the list, badged with the role that decides
    // what the screen offers you.
    expect(screen.getByText('Q3 Client Day')).toBeInTheDocument();
    expect(screen.getByText('Organising')).toBeInTheDocument();
  });

  it('puts a live event above the list with a way straight into it', async () => {
    show(<HomePage />);

    // The fixture's tournament is ROUND_IN_PROGRESS.
    expect(await screen.findByText('Playing')).toBeInTheDocument();
    // Exact: a row for an event at "Registration open" matches a loose /open/i.
    expect(screen.getByRole('link', { name: 'Open' })).toBeInTheDocument();
  });

  it('a tournament shows the field, the draw and the controls', async () => {
    show(<TournamentPage tournamentId={T} />);

    expect(await screen.findByText('Acme Corporate Day')).toBeInTheDocument();
    expect(await screen.findByText('Kim')).toBeInTheDocument();
    expect(screen.getByText(/no account/i)).toBeInTheDocument();
    expect(await screen.findByText(/Group 1/)).toBeInTheDocument();
  });

  it('tells a player which tee to walk to', async () => {
    // The shotgun start means this is the one fact nobody can infer: every group
    // goes off at once, so assuming the 1st sends a player to a tee that already
    // has somebody on it. The draw carried the hole numbers all along — the
    // screen simply never passed the course in, so the line rendered empty.
    show(<TournamentPage tournamentId={T} />);

    expect(await screen.findByText('Your group')).toBeInTheDocument();
    expect(await screen.findByText(/start on/i)).toHaveTextContent(/hole 7/i);
    // And the whole loop, on the group's row in the draw.
    expect(await screen.findByText('Holes 7, 8, 9')).toBeInTheDocument();
  });

  it('numbers the hole strip the way the course does, not 1-2-3', async () => {
    // A group on 7-9 that sees "1, 2, 3" is being shown a different hole. The
    // state stays in the accessible name so a label cannot silence it.
    show(<ScorePage groupId="group-1" />);

    for (const [number, state] of [
      [7, 'done'],
      [8, 'now'],
      [9, 'to play'],
    ] as const) {
      expect(
        await screen.findByRole('button', { name: new RegExp(`^hole ${number} — ${state}$`, 'i') }),
      ).toBeInTheDocument();
    }
    expect(screen.queryByRole('button', { name: /^loop hole/i })).not.toBeInTheDocument();
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

  it('shows fun rounds in the same list as tournaments', async () => {
    show(<HomePage />);

    // One list, both kinds. A fun round carries no role badge — everybody in one
    // is just playing.
    expect(await screen.findByText('Saturday nine')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /start a round/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /new tournament/i })).toBeInTheDocument();
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

    // The event's name leads now — there is nothing else on the screen to scan
    // against, so a heading above a card only delayed the answer.
    expect(await screen.findByText('Acme Corporate Day')).toBeInTheDocument();
    expect(screen.getByText(/Kim is running/)).toBeInTheDocument();
    expect(screen.getByText(CODE)).toBeInTheDocument();
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

  it('event settings is where a day becomes fourballs and a shotgun', async () => {
    // Both live on the event rather than on each draw, so rounds two and three
    // come out the same shape without the organiser restating anything.
    get.mockImplementation((path: string) =>
      path === `/tournaments/${T}`
        ? Promise.resolve({ ...TOURNAMENT, status: 'REGISTRATION_OPEN' })
        : path in ROUTES
          ? Promise.resolve(ROUTES[path])
          : Promise.reject(new Error(`unexpected GET ${path}`)),
    );

    show(<TournamentSettingsPage tournamentId={T} />);

    const size = (await screen.findByLabelText(/group size/i)) as HTMLSelectElement;
    const start = screen.getByLabelText(/^start$/i) as HTMLSelectElement;
    expect(size.value).toBe('3');
    expect(start.value).toBe('BLOCKS');

    await userEvent.selectOptions(size, '4');
    await userEvent.selectOptions(start, 'SHOTGUN');
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    expect(patch).toHaveBeenCalledWith(
      `/tournaments/${T}`,
      expect.objectContaining({ group_size: 4, loop_style: 'SHOTGUN' }),
    );
  });

  it('event settings does the shotgun arithmetic the organiser cannot', async () => {
    // The number that decides whether the day is a real shotgun or a queue: a
    // tee per group, and a course only has so many.
    get.mockImplementation((path: string) =>
      path === `/tournaments/${T}`
        ? Promise.resolve({ ...TOURNAMENT, status: 'REGISTRATION_OPEN' })
        : path in ROUTES
          ? Promise.resolve(ROUTES[path])
          : Promise.reject(new Error(`unexpected GET ${path}`)),
    );

    show(<TournamentSettingsPage tournamentId={T} />);

    const start = (await screen.findByLabelText(/^start$/i)) as HTMLSelectElement;
    await userEvent.selectOptions(start, 'SHOTGUN');

    // The fixture course has nine holes, so a shotgun has nine starting tees —
    // where blocks would give it three. That difference is the whole feature.
    expect(screen.getByText(/starts 9 groups at once/i)).toBeInTheDocument();
    expect(screen.getByText(/27 players in threes/i)).toBeInTheDocument();
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

  it('offers the three appearance choices, saying what system does', async () => {
    show(<StatsPage />);

    // By role, not text: the fieldset carries a visually-hidden legend of the
    // same name so the radio group is announced, which is correct and makes a
    // plain text query ambiguous.
    expect(await screen.findByRole('heading', { name: 'Appearance' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /system/i })).toBeChecked();
    expect(screen.getByRole('radio', { name: /light/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /dark/i })).toBeInTheDocument();
    // The behaviour that isn't obvious from the word "System".
    expect(screen.getByText(/scoring stays bright/i)).toBeInTheDocument();
  });

  it('asks for the bright treatment on the screens used outdoors', async () => {
    // The component's half of the sunlight rule. Whether it *wins* is CSS's
    // half — `[data-theme-source="system"] .lit` — which jsdom does not apply,
    // so this asserts the class is requested and theme.test.ts asserts the
    // attribute that decides it.
    const { container } = show(<ScorecardPage groupId="group-1" />);

    await screen.findByText(/how each hole went/i);
    expect(container.querySelector('main')).toHaveClass('lit');
  });

  it('puts your group above the organiser controls', async () => {
    show(<TournamentPage tournamentId={T} />);

    // Wait for the group specifically: it depends on the round query, and
    // findAllByRole resolves on the first heading to appear — which would
    // collect the list before the group has arrived and compare against -1.
    await screen.findByText('Your group');
    const headings = screen.getAllByRole('heading').map((h) => h.textContent ?? '');
    // By prefix: "The field" carries its count, so an exact match finds nothing
    // and the comparison silently passes on -1 < -1 being false.
    const at = (text: string) => headings.findIndex((h) => h.startsWith(text));

    // Mid-round the group is what the screen is opened for; the invite card is
    // what it was opened for a week earlier. Order is the whole point here.
    expect(at('Your group')).toBeGreaterThanOrEqual(0);
    expect(at('The field')).toBeGreaterThanOrEqual(0);
    expect(at('Your group')).toBeLessThan(at('The field'));
  });

  it('keeps every organiser control the artboard does not show', async () => {
    get.mockImplementation((path: string) =>
      path === `/tournaments/${T}`
        ? Promise.resolve({ ...TOURNAMENT, status: 'REGISTRATION_OPEN' })
        : path in ROUTES
          ? Promise.resolve(ROUTES[path])
          : Promise.reject(new Error(`unexpected GET ${path}`)),
    );

    show(<TournamentPage tournamentId={T} />);

    // The artboards are a visual target, not a feature list — a restyle that
    // quietly drops the state machine or the draw would still look right.
    expect(await screen.findByText('Run the day')).toBeInTheDocument();
    expect(screen.getByText('Remind the field')).toBeInTheDocument();
    expect(screen.getByText('Invite players')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /event settings/i })).toBeInTheDocument();
  });

  it('marks the tie-break as a question, not another card', async () => {
    // A hole the group still has to separate: strokes tied, no answer yet. The
    // server populates tied_participants only while that is true.
    get.mockImplementation((path: string) =>
      path === '/groups/group-1/scores'
        ? Promise.resolve({
            group_id: 'group-1',
            holes: [
              {
                ...(ROUTES['/groups/group-1/scores'] as { holes: object[] }).holes[0],
                tied_participants: ['p-kim', 'p-dave'],
              },
            ],
          })
        : path in ROUTES
          ? Promise.resolve(ROUTES[path])
          : Promise.reject(new Error(`unexpected GET ${path}`)),
    );

    show(<ScorePage groupId="group-1" />);

    // Score entry opens on the first hole *not* yet played, so reach the tied
    // one the way a player would — by pressing its chip. Named by the course's
    // hole number, which is the only name the group would recognise.
    await userEvent.click(await screen.findByRole('button', { name: /^hole 7/i }));

    // This is the one moment the screen asks rather than records, and it used to
    // look like every other card.
    expect(await screen.findByText(/tied on strokes/i)).toBeInTheDocument();
    // By role: the help panel on this screen previews the same question in prose,
    // and it is the heading — the screen actually asking — that this is about.
    expect(
      screen.getByRole('heading', { name: /who was closest to the pin/i }),
    ).toBeInTheDocument();
  });

  it('keeps the hole strip pressable, not decorative', async () => {
    show(<ScorePage groupId="group-1" />);

    // The restyle makes these read as state chips. They are still how somebody
    // goes back to a hole they mis-keyed, so they have to stay buttons with the
    // current one announced — the accessibility a decorative restyle drops.
    const holes = await screen.findAllByRole('button', { name: /now|done|to play/i });
    expect(holes.length).toBeGreaterThan(0);
    expect(holes.some((hole) => hole.getAttribute('aria-current') === 'true')).toBe(true);
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

describe('knockout', () => {
  const KO = { ...TOURNAMENT, format: 'KNOCKOUT', status: 'ROUND_COMPLETE' };

  function koRoutes(round: unknown, board?: unknown) {
    return {
      ...ROUTES,
      [`/tournaments/${T}`]: KO,
      '/rounds/round-1': round,
      ...(board ? { [`/tournaments/${T}/leaderboard`]: board } : {}),
    } as Record<string, unknown>;
  }

  function serve(routes: Record<string, unknown>) {
    get.mockImplementation((path: string) =>
      path in routes
        ? Promise.resolve(routes[path])
        : Promise.reject(new Error(`unexpected GET ${path}`)),
    );
  }

  it('tells a knocked-out player they are out, rather than showing them nothing', async () => {
    // The whole screen for 48 of a 64-player field. Before knockout existed,
    // having no group rendered `null` and the page simply forgot about them.
    const round = {
      ...(ROUTES['/rounds/round-1'] as { groups: unknown[] }),
      status: 'COMPLETE',
      round_number: 2,
      groups: [
        {
          id: 'group-9',
          round_id: 'round-1',
          group_number: 1,
          members: [{ participant_id: 'p-dave' }],
          holes: LOOP,
          advancing_participant_id: null,
          advanced_by: null,
        },
      ],
    };
    serve(koRoutes(round));

    show(<TournamentPage tournamentId={T} />);

    expect(await screen.findByText(/you're out/i)).toBeInTheDocument();
    expect(screen.getByText(/didn't go through to round 2/i)).toBeInTheDocument();
  });

  it('says how a group was decided, in words rather than the stored label', async () => {
    const round = {
      ...(ROUTES['/rounds/round-1'] as object),
      status: 'COMPLETE',
      groups: [
        {
          id: 'group-1',
          round_id: 'round-1',
          group_number: 1,
          members: [{ participant_id: 'p-kim' }, { participant_id: 'p-dave' }],
          holes: LOOP,
          advancing_participant_id: 'p-kim',
          advanced_by: 'countback',
        },
      ],
    };
    serve(koRoutes(round));

    show(<TournamentPage tournamentId={T} />);

    expect(await screen.findByText(/on countback/i)).toBeInTheDocument();
    // One group left and it has a winner, so the bracket is over.
    expect(screen.getByText(/wins the day/i)).toBeInTheDocument();
  });

  it('ranks the board by how far a player got, and says so', async () => {
    const board = {
      tournament_id: T,
      round_id: null,
      entries: [
        {
          position: 1,
          participant_id: 'p-kim',
          display_name: 'Kim',
          points: 0,
          total_strokes: 27,
          holes_played: 6,
          rounds_survived: 3,
        },
        {
          position: 2,
          participant_id: 'p-dave',
          display_name: 'Dave',
          points: 2,
          total_strokes: 25,
          holes_played: 3,
          rounds_survived: 1,
        },
      ],
    };
    serve(koRoutes(ROUTES['/rounds/round-1'], board));

    show(<LeaderboardPage tournamentId={T} />);

    expect(await screen.findByRole('columnheader', { name: 'Reached' })).toBeInTheDocument();
    expect(screen.getByText('Champion')).toBeInTheDocument();
    expect(screen.getByText('Out in R1')).toBeInTheDocument();
    // Kim scored fewer points than Dave and is still top — the point of ADR-012.
    expect(screen.getByText(/ranked by how far a player got/i)).toBeInTheDocument();
  });

  it('leaves the Reached column off a round-robin board', async () => {
    show(<LeaderboardPage tournamentId={T} />);

    await screen.findByRole('table');
    expect(screen.queryByRole('columnheader', { name: 'Reached' })).not.toBeInTheDocument();
    expect(screen.getByText(/level players are split by fewest total strokes/i)).toBeInTheDocument();
  });
});

/**
 * The explainer, and the help each screen carries.
 *
 * `docs/SCREENS.md` ranks this the highest-risk gap in the app, because it fails
 * at the worst moment: a guest who has never heard of the format, standing on a
 * tee, being asked how many strokes they took. So the two assertions that matter
 * are that the walkthrough opens on the format, and that the tie-break question
 * is reachable from score entry without leaving score entry.
 */
describe('how Threes works', () => {
  it('opens on the format, which is what nobody arrives knowing', async () => {
    show(<HowItWorksPage />);

    expect(await screen.findByText('Three holes, not eighteen')).toBeInTheDocument();
    expect(screen.getByText(/step 1 of/i)).toBeInTheDocument();
    // Nothing to go back to yet.
    expect(screen.queryByRole('button', { name: 'Back' })).not.toBeInTheDocument();
  });

  it('steps forward and back', async () => {
    show(<HowItWorksPage />);

    await userEvent.click(await screen.findByRole('button', { name: 'Next' }));
    expect(await screen.findByText('Your group is your match')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByText('Three holes, not eighteen')).toBeInTheDocument();
  });

  it('offers the organiser track only at the end of the player one', async () => {
    show(<HowItWorksPage />);

    expect(screen.queryByRole('button', { name: /how to run one/i })).not.toBeInTheDocument();

    // Walk to the end rather than counting taps: the number of player steps is
    // content, and a test that hardcodes it fails every time somebody writes a
    // new one — which is not a regression worth being told about.
    for (let guard = 0; guard < 20; guard += 1) {
      const next = screen.queryByRole('button', { name: 'Next' });
      if (!next) break;
      await userEvent.click(next);
    }

    // "Done" is a Link, so it is a link — the last step offers a way out of the
    // walkthrough rather than another step.
    expect(await screen.findByRole('link', { name: 'Done' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /how to run one/i }));
    expect(await screen.findByText('Setting up an event')).toBeInTheDocument();
  });

  it('answers the tie-break question on score entry, without leaving it', async () => {
    show(<ScorePage groupId="group-1" />);

    // Closed until asked for: the panel must not push the steppers down the
    // screen for the group who already know what they are doing.
    const summary = await screen.findByText('Entering scores');
    // A closed `<details>` keeps its content in the DOM, so this is about what
    // the group can *see* — visibility, not presence.
    expect(screen.getByText(/if two of you tie on strokes/i)).not.toBeVisible();

    await userEvent.click(summary);

    expect(screen.getByText(/if two of you tie on strokes/i)).toBeVisible();
    // Still on score entry — the panel offers the walkthrough, it does not go.
    expect(screen.getByRole('heading', { name: /Group/ })).toBeInTheDocument();
  });
});

/**
 * Handicaps (ADR-013), where they reach a screen.
 *
 * The allocation is the server's and is tested there. What matters here is that
 * a scratch event looks exactly as it did — no Net column, no handicap boxes —
 * and that a handicap event shows both numbers rather than quietly replacing
 * gross with net.
 */
describe('handicaps', () => {
  const HANDICAP_TOURNAMENT = { ...TOURNAMENT, status: 'REGISTRATION_OPEN', handicap_enabled: true };

  function serve(routes: Record<string, unknown>) {
    get.mockImplementation((path: string) =>
      path in routes
        ? Promise.resolve(routes[path])
        : Promise.reject(new Error(`unexpected GET ${path}`)),
    );
  }

  it('leaves a scratch board exactly as it was', async () => {
    show(<LeaderboardPage tournamentId={T} />);

    await screen.findByRole('table');
    expect(screen.queryByRole('columnheader', { name: 'Net' })).not.toBeInTheDocument();
    expect(screen.getByText(/level players are split by fewest total strokes/i)).toBeInTheDocument();
  });

  it('adds a Net column, and keeps gross beside it', async () => {
    serve({
      ...ROUTES,
      [`/tournaments/${T}/leaderboard`]: {
        tournament_id: T,
        round_id: null,
        entries: [
          {
            position: 1,
            participant_id: 'p-dave',
            display_name: 'Dave',
            points: 1,
            total_strokes: 21,
            holes_played: 3,
            rounds_survived: null,
            net_strokes: 18,
          },
        ],
      },
    });

    show(<LeaderboardPage tournamentId={T} />);

    expect(await screen.findByRole('columnheader', { name: 'Net' })).toBeInTheDocument();
    // Both numbers, neither replacing the other.
    expect(screen.getByText('21')).toBeInTheDocument();
    expect(screen.getByText('18')).toBeInTheDocument();
    expect(screen.getByText(/gross less the shots received/i)).toBeInTheDocument();
  });

  it('gives the organiser a handicap box per player, only on a handicap event', async () => {
    serve({ ...ROUTES, [`/tournaments/${T}`]: HANDICAP_TOURNAMENT });

    show(<TournamentPage tournamentId={T} />);

    expect(await screen.findByLabelText('Handicap for Kim')).toBeInTheDocument();
    expect(screen.getByLabelText('Handicap for Dave')).toBeInTheDocument();
    // And says which rows still need one, where the organiser is already looking
    // rather than only when the draw refuses.
    expect(screen.getAllByText(/no handicap/i)).toHaveLength(2);
  });

  it('shows no handicap boxes on a scratch event', async () => {
    serve({ ...ROUTES, [`/tournaments/${T}`]: { ...TOURNAMENT, status: 'REGISTRATION_OPEN' } });

    show(<TournamentPage tournamentId={T} />);

    await screen.findByText('Kim');
    expect(screen.queryByLabelText('Handicap for Kim')).not.toBeInTheDocument();
  });
});
