/**
 * Where everyone lands. Two lists, because the API answers two different
 * questions and conflating them would hide one of them.
 *
 * "Playing in" comes from `GET /players/me/tournaments`; "Organising" from
 * `GET /tournaments`. An organiser who also plays — the normal case for a
 * corporate day — appears in both, which is correct rather than duplication:
 * they have two roles and the screens differ.
 */

import { Link } from 'react-router-dom';

import { Card, Empty, ErrorNote, Loading, Page } from '../../components/ui';
import { useOrganising, usePlaying } from '../../lib/queries';
import { useSession } from '../auth/session-context';
import { signOut } from '../../lib/supabase';
import type { Tournament } from '../../lib/types';
import { readableStatus } from './format';

function TournamentList({ tournaments }: { tournaments: Tournament[] }) {
  return (
    <ul className="list">
      {tournaments.map((tournament) => (
        <li key={tournament.id}>
          <Link to={`/t/${tournament.id}`}>
            <span className="list-name">{tournament.name}</span>
            <span className="badge">{readableStatus(tournament.status)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function HomePage() {
  const { player } = useSession();
  const playing = usePlaying();
  const organising = useOrganising();

  return (
    <Page
      title="Threes"
      actions={
        <button type="button" className="ghost" onClick={() => void signOut()}>
          Sign out
        </button>
      }
    >
      <p className="muted">{player?.display_name ?? player?.email}</p>

      <Card>
        <h2>Playing in</h2>
        {playing.isPending && <Loading />}
        <ErrorNote error={playing.error} />
        {playing.data &&
          (playing.data.length ? (
            <TournamentList tournaments={playing.data} />
          ) : (
            <Empty>Nothing yet. An organiser will send you a link to join.</Empty>
          ))}
      </Card>

      <Card>
        <h2>Organising</h2>
        {organising.isPending && <Loading />}
        <ErrorNote error={organising.error} />
        {organising.data && organising.data.length > 0 && (
          <TournamentList tournaments={organising.data} />
        )}
        <Link to="/new" className="button-link">
          Set up a tournament
        </Link>
      </Card>
    </Page>
  );
}
