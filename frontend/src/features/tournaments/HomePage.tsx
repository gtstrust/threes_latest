/**
 * Where everyone lands, and — mid-round — the fastest way back to scoring.
 *
 * **One list, with a badge saying which you are.** This used to be two, on the
 * reasoning that `GET /players/me/tournaments` and `GET /tournaments` answer
 * different questions and merging them would hide one. True, but it made the
 * reader do the work: an organiser who also plays — the normal case for a
 * corporate day — appeared twice, and finding one event meant scanning two
 * lists. A badge on the row answers the same question in the place you are
 * already looking.
 *
 * The hero above it is what the screen is opened for during an event. Anything
 * being played right now gets promoted out of the list with the one action that
 * matters, so scoring is one tap from launch rather than three.
 */

import { Link } from 'react-router-dom';

import { Card, Empty, ErrorNote, Loading, Page } from '../../components/ui';
import { useFunRounds, useOrganising, usePlaying } from '../../lib/queries';
import { useSession } from '../auth/session-context';
import { signOut } from '../../lib/supabase';
import type { FunRound, Tournament, UUID } from '../../lib/types';
import { readableStatus } from './format';

/** One row of the list: an event of either kind, flattened. */
type Entry = {
  id: UUID;
  name: string;
  to: string;
  status: string;
  /** What you are in it. Null for a fun round, where everyone is just playing. */
  role: 'Playing' | 'Organising' | null;
  live: boolean;
};

const FUN_ROUND_LABEL: Record<FunRound['status'], string> = {
  lobby: 'Getting ready',
  playing: 'Playing',
  finished: 'Finished',
};

/**
 * Everything you are in, newest kind first, deduplicated.
 *
 * An event you organise *and* play appears once, badged "Organising" — that is
 * the more specific of the two roles and the one that changes what the screen
 * offers you.
 */
function entries(playing: Tournament[], organising: Tournament[], funRounds: FunRound[]): Entry[] {
  const organisedIds = new Set(organising.map((t) => t.id));
  const tournaments = [...organising, ...playing.filter((t) => !organisedIds.has(t.id))];

  return [
    ...funRounds.map((round) => ({
      id: round.id,
      name: round.name,
      to: `/r/${round.id}`,
      status: FUN_ROUND_LABEL[round.status],
      role: null,
      live: round.status === 'playing',
    })),
    ...tournaments.map((tournament) => ({
      id: tournament.id,
      name: tournament.name,
      to: `/t/${tournament.id}`,
      status: readableStatus(tournament.status),
      role: organisedIds.has(tournament.id) ? ('Organising' as const) : ('Playing' as const),
      live: tournament.status === 'ROUND_IN_PROGRESS',
    })),
  ];
}

export function HomePage() {
  const { player } = useSession();
  const playing = usePlaying();
  const organising = useOrganising();
  const funRounds = useFunRounds();

  const loading = playing.isPending || organising.isPending || funRounds.isPending;
  const error = playing.error ?? organising.error ?? funRounds.error;

  const all = entries(playing.data ?? [], organising.data ?? [], funRounds.data ?? []);
  const live = all.filter((entry) => entry.live);
  const rest = all.filter((entry) => !entry.live);

  return (
    <Page
      title={player?.display_name ?? 'Threes'}
      actions={
        <button type="button" className="ghost" onClick={() => void signOut()}>
          Sign out
        </button>
      }
    >
      <p className="muted small">
        {player?.display_name ? player.email : 'Signed in'} · <Link to="/me">Your golf</Link>
      </p>

      {live.map((entry) => (
        <LiveCard key={entry.id} entry={entry} />
      ))}

      <Card>
        <h2>Your events</h2>
        {loading && <Loading />}
        <ErrorNote error={error} />
        {!loading && rest.length === 0 && live.length === 0 && (
          <Empty>Nothing yet. Start a round, or open a link somebody sent you.</Empty>
        )}
        {rest.length > 0 && (
          <ul className="list">
            {rest.map((entry) => (
              <li key={entry.id}>
                <Link to={entry.to}>
                  <span className="list-name">{entry.name}</span>
                  <span className="row-tail">
                    {entry.role && <span className="badge">{entry.role}</span>}
                    <span className="muted small">{entry.status}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="button-pair">
        <Link to="/rounds/new" className="button-link ghost">
          Start a round
        </Link>
        <Link to="/new" className="button-link ghost">
          New tournament
        </Link>
      </div>
    </Page>
  );
}

/**
 * An event being played right now, promoted out of the list.
 *
 * **No score on it, deliberately.** The artboard showed points, and getting them
 * honestly costs two requests — the leaderboard, plus the field to learn which
 * participant is you. Matching on display name instead would be wrong on exactly
 * the case the domain allows for: two people really can both be John Smith.
 *
 * The card's job is "this is live, here is the way in". A number that is right
 * most of the time is worth less than one tap.
 */
function LiveCard({ entry }: { entry: Entry }) {
  return (
    <Card>
      <span className="badge live">Playing</span>
      <h2 className="live-name">{entry.name}</h2>
      <Link to={entry.to} className="button-link">
        Open
      </Link>
    </Card>
  );
}
