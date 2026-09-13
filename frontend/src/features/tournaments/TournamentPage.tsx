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
import { HelpPanel } from '../help/HelpPanel';
import {
  useAddVirtualPlayer,
  useCompleteRound,
  useCourse,
  useAdjudicate,
  useDrawRound,
  useField,
  useJoinTournament,
  useRemoveParticipant,
  useRound,
  useRounds,
  useSendReminder,
  useSetStatus,
  useTournament,
} from '../../lib/queries';
import { ApiError } from '../../lib/api';
import { useSession } from '../auth/session-context';
import { InviteCard } from '../invite/InviteCard';
import type {
  CourseWithHoles,
  Participant,
  Round,
  RoundWithGroups,
  Tournament,
  UUID,
} from '../../lib/types';
import { parseHoles, readableGroupSize, readableStatus } from './format';
import { bracketRounds } from './knockout';
import { readableWhen } from './when';
import { GroupList } from '../rounds/GroupList';
import { loopHoles, loopLabel } from '../rounds/loop';

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
  const adjudicate = useAdjudicate(tournamentId, current?.id);

  const [virtualName, setVirtualName] = useState('');
  const [holeText, setHoleText] = useState('');

  if (tournament.isPending) return <Loading what="Loading tournament" />;

  // Reading a tournament is restricted to the organiser and the field, so a 403
  // means someone arrived holding the app URL rather than a join link. Saying
  // what to do about it beats showing them the guard's own sentence.
  if (tournament.error instanceof ApiError && tournament.error.status === 403)
    return (
      <Page title="Tournament" back={{ to: '/', label: 'Tournaments' }}>
        <Card>
          <h2>You&rsquo;re not in this event</h2>
          <p className="muted">
            Ask the organiser for the join link — it looks like{' '}
            <code>{window.location.origin}/join/THR-…</code> — or scan their QR code.
          </p>
        </Card>
      </Page>
    );

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
  const isFull = event.max_players !== null && (field.data?.length ?? 0) >= event.max_players;

  const isKnockout = event.format === 'KNOCKOUT';
  // How many rounds the bracket takes, from the field it started with — the
  // draw shrinks every round, so the *current* round's players would give a
  // smaller and steadily wrong answer.
  const bracketLength = isKnockout
    ? bracketRounds(field.data?.length ?? 0, event.group_size === 4 ? 4 : 3).length
    : 0;
  const stillIn = round.data
    ? round.data.groups.reduce((total, group) => total + group.members.length, 0)
    : 0;
  // The final is one group, and once it has finished somebody has won it.
  const champion =
    isKnockout && round.data?.groups.length === 1
      ? round.data.groups[0].advancing_participant_id
      : null;

  return (
    <Page
      title={event.name}
      back={{ to: '/', label: 'Tournaments' }}
      actions={
        <span className={status === 'ROUND_IN_PROGRESS' ? 'badge live' : 'badge'}>
          {readableStatus(status)}
        </span>
      }
    >
      <p className="muted small meta">
        {[course.data?.name, readableWhen(event.scheduled_at)].filter(Boolean).join(' · ') ||
          'No course or date set yet'}
      </p>

      {/* One route, two jobs — an organiser needs to know how to run the day, a
          player needs to know what their group is. A corporate organiser usually
          plays too, so this follows the same `isOrganiser` branch the rest of the
          screen does rather than inventing a third state. */}
      <HelpPanel topic={isOrganiser ? 'run-the-day' : 'your-group'} />

      {isKnockout && round.data && (
        <p className="muted small meta">
          Knockout · round {round.data.round_number}
          {bracketLength ? ` of ${bracketLength}` : ''} · {stillIn} player
          {stillIn === 1 ? '' : 's'} left
        </p>
      )}

      {/* --- The player's own place in it -------------------------------- */}
      {!me && status === 'REGISTRATION_OPEN' && (
        <Card>
          <h2>Join</h2>
          {isFull ? (
            // Said out loud rather than shown as a disabled button with no
            // explanation — "full" is information, not a failure.
            <p className="muted">
              This event is full — the organiser capped it at {event.max_players} players.
            </p>
          ) : (
            <button type="button" onClick={() => join.mutate()} disabled={join.isPending}>
              {join.isPending ? 'Joining…' : "I'm playing"}
            </button>
          )}
          <ErrorNote error={join.error} />
        </Card>
      )}

      {me && round.data && (
        <MyGroup
          round={round.data}
          participantId={me.id}
          field={field.data ?? []}
          course={course.data}
          eliminated={isKnockout}
        />
      )}

      {(status === 'ROUND_IN_PROGRESS' ||
        status === 'ROUND_COMPLETE' ||
        status === 'TOURNAMENT_COMPLETE') && (
        <Link to={`/t/${tournamentId}/leaderboard`} className="button-link">
          Leaderboard
        </Link>
      )}

      {/* --- The field ---------------------------------------------------- */}
      <Card>
        <h2>
          The field{' '}
          {field.data
            ? event.max_players
              ? `(${field.data.length} of ${event.max_players})`
              : `(${field.data.length})`
            : ''}
        </h2>
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

      {/* --- Handing the event out ---------------------------------------- */}
      {isOrganiser && event.join_code && FIELD_IS_EDITABLE.includes(status) && (
        <InviteCard
          code={event.join_code}
          blurb="Players scan this or follow the link, sign in, and they're in the field."
          tournamentId={tournamentId}
        />
      )}

      {isOrganiser && FIELD_IS_EDITABLE.includes(status) && (
        <Link to={`/t/${tournamentId}/settings`} className="button-link">
          Event settings
        </Link>
      )}

      {isOrganiser && FIELD_IS_EDITABLE.includes(status) && (
        <RemindField tournamentId={tournamentId} />
      )}

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
              {/* How this draw will come out. It is decided on another screen,
                  and every round of the event inherits it, so it is worth
                  saying here rather than leaving the organiser to remember. */}
              <p className="muted small">
                {readableGroupSize(tournament.data.group_size)} ·{' '}
                {tournament.data.loop_style === 'SHOTGUN' ? 'shotgun start' : 'blocks start'} ·{' '}
                <Link to={`/t/${tournamentId}/settings`}>Change</Link>
              </p>

              <label htmlFor="holes">Holes to play (optional)</label>
              {/* For a match inside a normal round — "7, 8, 9 are the comp".
                  Omitted plays the whole course. What a selection has to look
                  like depends on the start style: a blocks draw needs a multiple
                  of three, a shotgun needs only three, since every hole in it is
                  a starting tee. The server owns that rule. */}
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

          {champion && (
            <p className="start-hole">
              <strong>{nameOf(field.data ?? [], champion)}</strong> wins the day.
            </p>
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
          <ErrorNote error={adjudicate.error} />
          <GroupList
            round={round.data}
            field={field.data ?? []}
            myParticipantId={me?.id}
            course={course.data}
            showAdvancement={isKnockout && round.data.status === 'COMPLETE'}
            onAdjudicate={
              isOrganiser
                ? (groupId, participantId) =>
                    adjudicate.mutate({ groupId, participantId })
                : undefined
            }
          />
        </Card>
      )}
    </Page>
  );
}

/**
 * Mailing the field about the event.
 *
 * Reports the count the API returns rather than "sent!", because zero is a real
 * answer — a field of players added by hand has no addresses to write to, and an
 * organiser who is told "sent" would go on believing they had been.
 */
function RemindField({ tournamentId }: { tournamentId: UUID }) {
  const remind = useSendReminder(tournamentId);

  return (
    <Card>
      <h2>Remind the field</h2>
      <p className="muted small">
        Emails everyone with an account about the event, with a link to their group. Players you
        added yourself have no address to write to.
      </p>
      <button type="button" onClick={() => remind.mutate()} disabled={remind.isPending}>
        {remind.isPending ? 'Sending…' : 'Send a reminder'}
      </button>
      {remind.data && (
        <p className="muted small">
          {remind.data.sent === 0
            ? 'Nobody in this field has an account to email.'
            : `Sent to ${remind.data.sent} ${remind.data.sent === 1 ? 'player' : 'players'}.`}
        </p>
      )}
      <ErrorNote error={remind.error} />
    </Card>
  );
}

/**
 * Where this player is meant to be, and who with.
 *
 * The tee leads, because a shotgun start makes it the one fact nobody can infer:
 * every group goes off at once, so a player who assumes the 1st walks to a tee
 * that already has somebody else on it. Stated only once the course has resolved
 * real numbers — `loopLabel` returns null rather than guessing, since a
 * confidently wrong hole number is worse here than no hole number at all.
 */
function MyGroup({
  round,
  participantId,
  field,
  course,
  eliminated = false,
}: {
  round: RoundWithGroups;
  participantId: UUID;
  field: Participant[];
  course?: CourseWithHoles;
  /** Whether having no group means "knocked out" rather than "something broke". */
  eliminated?: boolean;
}) {
  const mine = round.groups.find((group) =>
    group.members.some((member) => member.participant_id === participantId),
  );

  // Being in no group is normal in a knockout and means one thing: you are out.
  // Returning null — the only behaviour before knockout existed — would leave an
  // eliminated player looking at a page that simply forgot about them, which is
  // most of a 64-player field. On a round robin a missing group really would be
  // a bug, and silence is still the honest answer there.
  if (!mine) {
    if (!eliminated) return null;
    return (
      <Card>
        <h2>You're out</h2>
        <p className="muted">
          You didn't go through to round {round.round_number}. Thanks for playing — the
          leaderboard has where you finished.
        </p>
      </Card>
    );
  }

  const others = mine.members
    .filter((member) => member.participant_id !== participantId)
    .map((member) => field.find((p) => p.id === member.participant_id)?.display_name)
    .filter(Boolean);

  const loop = loopHoles(mine.holes, course);
  const start = loop[0]?.known ? loop[0] : undefined;
  const holes = loopLabel(loop);

  return (
    <Card className="accent">
      <h2>Your group</h2>
      {start && (
        <p className="start-hole">
          Start on <strong>hole {start.label}</strong>
        </p>
      )}
      <p className="muted">
        Playing with {others.join(', ') || 'nobody yet'}
        {holes && ` · ${holes.toLowerCase()}`}
      </p>
      <Link to={`/g/${mine.id}`} className="button-link primary">
        Enter scores
      </Link>
    </Card>
  );
}

/** A participant's name, for the few places outside GroupList that need one. */
function nameOf(field: Participant[], id: UUID): string {
  return field.find((participant) => participant.id === id)?.display_name ?? 'The winner';
}
