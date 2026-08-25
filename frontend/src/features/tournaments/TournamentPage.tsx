/**
 * One tournament: the organiser's control panel, and the player's way in.
 *
 * One screen for both roles rather than two, because most of it is the same
 * information and the roles overlap — a corporate organiser usually plays too.
 * What differs is which buttons appear, and that follows from
 * `tournament.organiser_id`, the same fact the API authorises on.
 *
 * **The state machine is ADR-003 and the UI must not invent transitions.**
 * `POST /status` handles the registration moves and the final one; it *refuses*
 * `ROUND_IN_PROGRESS` and `ROUND_COMPLETE` (ADR-008) because drawing a round is
 * what starts play and completing one is what ends it. So those never appear as
 * buttons here — the draw button is the transition.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Card, Empty, ErrorNote, Loading, Page } from '../../components/ui';
import {
  useAddVirtualPlayer,
  useCompleteRound,
  useCourse,
  useDrawRound,
  useField,
  useJoinTournament,
  useRemoveParticipant,
  useRound,
  useRounds,
  useSetStatus,
  useTournament,
} from '../../lib/queries';
import { useSession } from '../auth/session-context';
import type { Participant, Round, Tournament, UUID } from '../../lib/types';
import { parseHoles, readableStatus } from './format';
import { GroupList } from '../rounds/GroupList';

/** The field is fixed once play starts, so the editing controls disappear then. */
const FIELD_IS_EDITABLE: Tournament['status'][] = [
  'CREATED',
  'REGISTRATION_OPEN',
  'REGISTRATION_CLOSED',
];

function latestRound(rounds: Round[] | undefined): Round | undefined {
  if (!rounds?.length) return undefined;
  return [...rounds].sort((a, b) => b.round_number - a.round_number)[0];
}

export function TournamentPage({ tournamentId }: { tournamentId: UUID }) {
  const { player } = useSession();
  const tournament = useTournament(tournamentId);
  const field = useField(tournamentId);
  const rounds = useRounds(tournamentId);
  const current = latestRound(rounds.data);
  const round = useRound(current?.id);
  const course = useCourse(tournament.data?.course_id);

  const setStatus = useSetStatus(tournamentId);
  const addVirtual = useAddVirtualPlayer(tournamentId);
  const removeParticipant = useRemoveParticipant(tournamentId);
  const join = useJoinTournament(tournamentId);
  const draw = useDrawRound(tournamentId);
  const complete = useCompleteRound(tournamentId);

  const [virtualName, setVirtualName] = useState('');
  const [holeText, setHoleText] = useState('');

  if (tournament.isPending) return <Loading what="Loading tournament" />;
  if (tournament.error)
    return (
      <Page title="Tournament" back={{ to: '/', label: 'Tournaments' }}>
        <ErrorNote error={tournament.error} />
      </Page>
    );

  const event = tournament.data!;
  const isOrganiser = event.organiser_id === player?.id;
  const me = field.data?.find((p) => p.player_id === player?.id);
  const status = event.status;

  return (
    <Page title={event.name} back={{ to: '/', label: 'Tournaments' }}>
      <p>
        <span className="badge">{readableStatus(status)}</span>
        {course.data && <span className="muted"> · {course.data.name}</span>}
      </p>

      {(status === 'ROUND_IN_PROGRESS' || status === 'ROUND_COMPLETE' ||
        status === 'TOURNAMENT_COMPLETE') && (
        <Link to={`/t/${tournamentId}/leaderboard`} className="button-link">
          Leaderboard
        </Link>
      )}

      {/* --- The player's own place in it -------------------------------- */}
      {!me && status === 'REGISTRATION_OPEN' && (
        <Card>
          <h2>Join</h2>
          <button type="button" onClick={() => join.mutate()} disabled={join.isPending}>
            {join.isPending ? 'Joining…' : "I'm playing"}
          </button>
          <ErrorNote error={join.error} />
        </Card>
      )}

      {me && round.data && (
        <MyGroup round={round.data} participantId={me.id} field={field.data ?? []} />
      )}

      {/* --- The field ---------------------------------------------------- */}
      <Card>
        <h2>The field {field.data ? `(${field.data.length})` : ''}</h2>
        {field.isPending && <Loading />}
        <ErrorNote error={field.error ?? removeParticipant.error} />
        {field.data?.length === 0 && <Empty>Nobody has joined yet.</Empty>}
        <ul className="list plain">
          {field.data?.map((participant) => (
            <li key={participant.id}>
              <span>
                {participant.display_name}
                {participant.is_virtual && <span className="muted small"> · no account</span>}
              </span>
              {isOrganiser && FIELD_IS_EDITABLE.includes(status) && (
                <button
                  type="button"
                  className="ghost danger"
                  aria-label={`Remove ${participant.display_name}`}
                  onClick={() => removeParticipant.mutate(participant.id)}
                >
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>

        {isOrganiser && FIELD_IS_EDITABLE.includes(status) && (
          <form
            onSubmit={(submit) => {
              submit.preventDefault();
              addVirtual.mutate(virtualName, { onSuccess: () => setVirtualName('') });
            }}
          >
            <label htmlFor="virtual">Add someone without a phone</label>
            {/* A Virtual Player is scored by whoever they walk round with. Names
                are not unique — two people really can both be John Smith. */}
            <input
              id="virtual"
              value={virtualName}
              onChange={(change) => setVirtualName(change.target.value)}
              placeholder="Dave"
            />
            <button type="submit" disabled={!virtualName || addVirtual.isPending}>
              Add player
            </button>
            <ErrorNote error={addVirtual.error} />
          </form>
        )}
      </Card>

      {/* --- Running the day ---------------------------------------------- */}
      {isOrganiser && (
        <Card>
          <h2>Run the day</h2>
          <ErrorNote error={setStatus.error ?? draw.error ?? complete.error} />

          {status === 'CREATED' && (
            <button type="button" onClick={() => setStatus.mutate('REGISTRATION_OPEN')}>
              Open registration
            </button>
          )}

          {status === 'REGISTRATION_OPEN' && (
            <button type="button" onClick={() => setStatus.mutate('REGISTRATION_CLOSED')}>
              Close registration
            </button>
          )}

          {(status === 'REGISTRATION_CLOSED' || status === 'ROUND_COMPLETE') && (
            <>
              <label htmlFor="holes">Holes to play (optional)</label>
              {/* For a match inside a normal round — "7, 8, 9 are the comp".
                  Omitted plays the whole course. A selection has to be a
                  multiple of three, since a loop is three holes. */}
              <input
                id="holes"
                inputMode="numeric"
                value={holeText}
                onChange={(change) => setHoleText(change.target.value)}
                placeholder="e.g. 7, 8, 9 — leave blank for the whole course"
              />
              <button
                type="button"
                onClick={() => draw.mutate(parseHoles(holeText))}
                disabled={draw.isPending}
              >
                {draw.isPending ? 'Drawing…' : `Draw round ${(rounds.data?.length ?? 0) + 1}`}
              </button>
            </>
          )}

          {status === 'ROUND_IN_PROGRESS' && current && (
            <button
              type="button"
              onClick={() => complete.mutate(current.id)}
              disabled={complete.isPending}
            >
              {complete.isPending ? 'Finishing…' : `Finish round ${current.round_number}`}
            </button>
          )}

          {status === 'ROUND_COMPLETE' && (
            <button type="button" onClick={() => setStatus.mutate('TOURNAMENT_COMPLETE')}>
              Finish the tournament
            </button>
          )}
        </Card>
      )}

      {/* --- The draw ------------------------------------------------------ */}
      {round.data && (
        <Card>
          <h2>
            Round {round.data.round_number}
            <span className="muted small"> · {round.data.groups.length} groups</span>
          </h2>
          <GroupList round={round.data} field={field.data ?? []} myParticipantId={me?.id} />
        </Card>
      )}
    </Page>
  );
}

function MyGroup({
  round,
  participantId,
  field,
}: {
  round: { groups: { id: UUID; group_number: number; members: { participant_id: UUID }[] }[] };
  participantId: UUID;
  field: Participant[];
}) {
  const mine = round.groups.find((group) =>
    group.members.some((member) => member.participant_id === participantId),
  );
  if (!mine) return null;

  const others = mine.members
    .filter((member) => member.participant_id !== participantId)
    .map((member) => field.find((p) => p.id === member.participant_id)?.display_name)
    .filter(Boolean);

  return (
    <Card>
      <h2>Your group</h2>
      <p className="muted">Playing with {others.join(', ') || 'nobody yet'}</p>
      <Link to={`/g/${mine.id}`} className="button-link primary">
        Enter scores
      </Link>
    </Card>
  );
}

