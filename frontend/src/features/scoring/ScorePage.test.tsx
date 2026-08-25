/**
 * The tie-break conversation, driven through the screen a player actually uses.
 *
 * `cascade.test.ts` proves the rule in isolation; this proves the screen asks
 * the right question of the right people and sends the right thing back. The
 * fixtures are real response shapes, checked against a running API: a tied hole
 * comes back `no_winner` with `tied_participants` populated and both tie-break
 * columns null, and a pin answer that names a tied player always settles it.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const get = vi.fn();
const post = vi.fn();
vi.mock('../../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../../lib/api')>('../../lib/api');
  return { ...actual, api: { get: (p: string) => get(p), post: (p: string, b: unknown) => post(p, b) } };
});

const { ScorePage } = await import('./ScorePage');

const GROUP = 'group-1';
const TOURNAMENT = 'tournament-1';
const HOLE = 'hole-1';
const KIM = 'participant-kim';
const PRIYA = 'participant-priya';
const DAVE = 'participant-dave';

function scores(k: number, p: number, d: number) {
  return [
    { participant_id: KIM, strokes: k, points: 0 },
    { participant_id: PRIYA, strokes: p, points: 0 },
    { participant_id: DAVE, strokes: d, points: 0 },
  ];
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockImplementation((path: string) => {
    if (path === `/groups/${GROUP}`)
      return Promise.resolve({
        id: GROUP,
        round_id: 'round-1',
        group_number: 1,
        members: [KIM, PRIYA, DAVE].map((participant_id) => ({ participant_id })),
        holes: [{ hole_id: HOLE, sequence: 1 }],
      });
    if (path === '/rounds/round-1')
      return Promise.resolve({
        id: 'round-1',
        tournament_id: TOURNAMENT,
        round_number: 1,
        status: 'IN_PROGRESS',
        created_at: '',
        updated_at: '',
        groups: [],
      });
    if (path === `/groups/${GROUP}/scores`) return Promise.resolve({ group_id: GROUP, holes: [] });
    if (path === `/tournaments/${TOURNAMENT}/participants`)
      return Promise.resolve([
        { id: KIM, display_name: 'Kim', is_virtual: false, player_id: 'x' },
        { id: PRIYA, display_name: 'Priya', is_virtual: false, player_id: 'y' },
        { id: DAVE, display_name: 'Dave', is_virtual: true, player_id: null },
      ]);
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ScorePage groupId={GROUP} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const TIED = {
  hole_id: HOLE,
  winner_participant_id: null,
  decided_by: 'no_winner',
  closest_to_pin_participant_id: null,
  longest_drive_participant_id: null,
  scores: scores(4, 4, 5),
  tied_participants: [KIM, PRIYA],
  created_at: '',
  updated_at: '',
};

describe('score entry', () => {
  it('asks nothing when the strokes settle it', async () => {
    post.mockResolvedValue({
      ...TIED,
      winner_participant_id: KIM,
      decided_by: 'strokes',
      scores: scores(3, 5, 4),
      tied_participants: [],
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /save hole/i }));

    expect(await screen.findByText(/takes it/i)).toHaveTextContent('Kim');
    expect(screen.queryByText(/closest to the pin/i)).not.toBeInTheDocument();
  });

  it('offers only the tied players when the strokes tie', async () => {
    post.mockResolvedValue(TIED);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /save hole/i }));

    // Dave played the hole and is irrelevant — ADR-007 contests the tie-break
    // among the tied players alone, and naming anyone else is a 422.
    const question = await screen.findByText(/who was closest to the pin/i);
    const card = question.closest('section')!;
    expect(within(card).getByRole('button', { name: 'Kim' })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Priya' })).toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: 'Dave' })).not.toBeInTheDocument();
  });

  it('re-posts the same hole with the pin answer', async () => {
    post.mockResolvedValueOnce(TIED).mockResolvedValueOnce({
      ...TIED,
      winner_participant_id: PRIYA,
      decided_by: 'closest_to_pin',
      closest_to_pin_participant_id: PRIYA,
      tied_participants: [],
    });
    const user = userEvent.setup();
    renderPage();

    // Dave takes 5, so the fixture's two-way tie is what these strokes imply.
    await user.click(await screen.findByRole('button', { name: /one more for Dave/i }));
    await user.click(screen.getByRole('button', { name: /save hole/i }));
    await user.click(await screen.findByRole('button', { name: 'Priya' }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    // The whole hole goes again — strokes and all. There is no tie-break
    // endpoint; the same upsert carries a correction and a late answer alike.
    expect(post.mock.calls[1][1]).toEqual({
      strokes: { [KIM]: 4, [PRIYA]: 4, [DAVE]: 5 },
      closest_to_pin: PRIYA,
    });
    expect(await screen.findByText(/takes it/i)).toHaveTextContent('Priya');
  });

  it('falls through to longest drive when the group declines the pin question', async () => {
    // Declining sends nothing, so the response cannot record it — the screen has
    // to remember. This is the case that would loop forever if it did not.
    post.mockResolvedValue(TIED);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /save hole/i }));
    await user.click(await screen.findByRole('button', { name: /nobody reached the green/i }));

    expect(await screen.findByText(/longest drive on the fairway/i)).toBeInTheDocument();
    // Declining must not post anything; the hole already stands as it is.
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('says nobody wins once both questions are declined', async () => {
    post.mockResolvedValue(TIED);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /save hole/i }));
    await user.click(await screen.findByRole('button', { name: /nobody reached the green/i }));
    await user.click(await screen.findByRole('button', { name: /nobody found the fairway/i }));

    expect(await screen.findByText(/nobody wins this hole/i)).toBeInTheDocument();
    expect(screen.getByText(/scores zero/i)).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('sends the strokes the steppers show', async () => {
    post.mockResolvedValue(TIED);
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /one more for Kim/i }));
    await user.click(await screen.findByRole('button', { name: /one fewer for Priya/i }));
    await user.click(screen.getByRole('button', { name: /save hole/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][1]).toEqual({ strokes: { [KIM]: 5, [PRIYA]: 3, [DAVE]: 4 } });
  });

  it('never lets strokes fall below one', async () => {
    // The API rejects anything under 1, and a stepper that can reach 0 turns a
    // rule into an error message the player has to read on a green.
    const user = userEvent.setup();
    renderPage();

    const fewer = await screen.findByRole('button', { name: /one fewer for Kim/i });
    for (let i = 0; i < 6; i += 1) await user.click(fewer);

    expect(screen.getByLabelText(/strokes for Kim/i)).toHaveTextContent('1');
  });
});
