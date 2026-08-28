/**
 * One fun round, across its whole short life: a lobby you fill and share, the
 * group once it's playing, and the finished card.
 *
 * There is no "run the day" ceremony here — a fun round is the host and a few
 * mates, so the controls collapse to join, add a no-phone mate, start, finish.
 * The host simply is the organiser underneath, which is why the same scoring and
 * leaderboard screens serve both.
 */

import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { Card, Empty, ErrorNote, Loading, Page } from '../../components/ui';
import {
  useAddVirtualToFunRound,
  useFinishFunRound,
  useFunRound,
  useFunRoundPreview,
  useJoinFunRound,
  useStartFunRound,
} from '../../lib/queries';
import { ApiError } from '../../lib/api';
import { useSession } from '../auth/session-context';
import type { FunRoundDetail, Participant, RoundWithGroups, UUID } from '../../lib/types';

export function FunRoundPage({ funRoundId }: { funRoundId: UUID }) {
  const funRound = useFunRound(funRoundId);
  const { player } = useSession();

  if (funRound.isPending) return <Loading what="Loading the round" />;

  // A 403 here is the normal way a mate arrives: they tapped the shared link and
  // aren't in the field yet. That is an invitation, not an error — the preview is
  // open to anyone signed in precisely so this screen can exist.
  if (funRound.error instanceof ApiError && funRound.error.status === 403)
    return <Invitation funRoundId={funRoundId} />;

  if (funRound.error || !funRound.data)
    return (
      <Page title="Fun round" back={{ to: '/', label: 'Home' }}>
        <ErrorNote error={funRound.error} />
      </Page>
    );

  const detail = funRound.data;
  const isHost = detail.host_id === player?.id;
  const inField = detail.participants.some((p) => p.player_id === player?.id);

  return (
    <Page
      title={detail.name}
      back={{ to: '/', label: 'Home' }}
      actions={<Link to={`/r/${funRoundId}/leaderboard`}>Leaderboard</Link>}
    >
      {detail.status === 'lobby' && <Lobby detail={detail} isHost={isHost} inField={inField} />}

      {detail.status === 'playing' && player && (
        <Playing
          detail={detail}
          isHost={isHost}
          participantId={playerParticipantId(detail, player.id)}
        />
      )}

      {detail.status === 'finished' && (
        <Card>
          <h2>That&rsquo;s a wrap</h2>
          <p className="muted">The round is done.</p>
          <Link to={`/r/${funRoundId}/leaderboard`} className="button-link">
            See the final board
          </Link>
        </Card>
      )}
    </Page>
  );
}

function playerParticipantId(detail: FunRoundDetail, playerId: UUID): UUID | null {
  return detail.participants.find((p) => p.player_id === playerId)?.id ?? null;
}

/**
 * What you see when the link reaches you before the round does.
 *
 * Deliberately thin — the host, how many are in, and one button. Who is playing
 * stays private until you are one of them, which is why this reads the preview
 * rather than the round.
 */
function Invitation({ funRoundId }: { funRoundId: UUID }) {
  const preview = useFunRoundPreview(funRoundId);
  const join = useJoinFunRound(funRoundId);

  if (preview.isPending) return <Loading what="Loading the invite" />;
  if (preview.error || !preview.data)
    return (
      <Page title="Fun round" back={{ to: '/', label: 'Home' }}>
        <ErrorNote error={preview.error} />
      </Page>
    );

  const invite = preview.data;
  const closed = invite.status !== 'lobby';

  return (
    <Page title={invite.name} back={{ to: '/', label: 'Home' }}>
      <Card>
        <h2>You&rsquo;re invited</h2>
        <p className="muted">
          {invite.host_name} is playing a fun round — {invite.player_count} in so far.
        </p>
        {closed ? (
          <p className="muted small">
            {invite.status === 'playing'
              ? 'They’ve already teed off, so joining is closed.'
              : 'This round has finished.'}
          </p>
        ) : invite.is_full ? (
          <p className="muted small">The group is full — a fun round is up to four players.</p>
        ) : (
          <button type="button" onClick={() => join.mutate()} disabled={join.isPending}>
            {join.isPending ? 'Joining…' : "I'm in"}
          </button>
        )}
        <ErrorNote error={join.error} />
      </Card>
    </Page>
  );
}

function Lobby({
  detail,
  isHost,
  inField,
}: {
  detail: FunRoundDetail;
  isHost: boolean;
  inField: boolean;
}) {
  const join = useJoinFunRound(detail.id);
  const start = useStartFunRound(detail.id);
  const full = detail.participants.length >= 4;

  return (
    <>
      <ShareCard funRoundId={detail.id} />

      <Card>
        <h2>Who&rsquo;s in</h2>
        <FieldList participants={detail.participants} />
        {!inField && (
          <button type="button" onClick={() => join.mutate()} disabled={join.isPending || full}>
            {join.isPending ? 'Joining…' : full ? 'Group is full' : "I'm in"}
          </button>
        )}
        <ErrorNote error={join.error} />
      </Card>

      {isHost && <AddVirtual funRoundId={detail.id} disabled={full} />}

      {isHost && (
        <Card>
          <h2>Start</h2>
          {detail.course_id ? (
            <>
              <p className="muted small">
                {detail.hole_numbers
                  ? `Playing holes ${detail.hole_numbers.join(', ')}.`
                  : 'Playing the first three holes of the course.'}{' '}
                Tees off the whole group at once. You need at least two players.
              </p>
              <button
                type="button"
                onClick={() => start.mutate(undefined)}
                disabled={start.isPending || detail.participants.length < 2}
              >
                {start.isPending ? 'Starting…' : 'Start the round'}
              </button>
            </>
          ) : (
            <p className="muted">
              This round has no course, so there are no holes to play. Start a new one and pick a
              course.
            </p>
          )}
          <ErrorNote error={start.error} />
        </Card>
      )}
    </>
  );
}

function Playing({
  detail,
  isHost,
  participantId,
}: {
  detail: FunRoundDetail;
  isHost: boolean;
  participantId: UUID | null;
}) {
  const finish = useFinishFunRound(detail.id);
  const round = detail.round;

  return (
    <>
      {round && participantId && (
        <MyGroup
          round={round}
          participantId={participantId}
          field={detail.participants}
          funRoundId={detail.id}
        />
      )}

      <Card>
        <h2>Leaderboard</h2>
        <Link to={`/r/${detail.id}/leaderboard`} className="button-link">
          See how it&rsquo;s going
        </Link>
      </Card>

      {isHost && (
        <Card>
          <h2>Finish</h2>
          <p className="muted small">Ends the round and locks the board.</p>
          <button
            type="button"
            className="ghost"
            onClick={() => finish.mutate()}
            disabled={finish.isPending}
          >
            {finish.isPending ? 'Finishing…' : 'Finish the round'}
          </button>
          <ErrorNote error={finish.error} />
        </Card>
      )}
    </>
  );
}

function MyGroup({
  round,
  participantId,
  field,
  funRoundId,
}: {
  round: RoundWithGroups;
  participantId: UUID;
  field: Participant[];
  funRoundId: UUID;
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
      <Link to={`/r/${funRoundId}/g/${mine.id}`} className="button-link primary">
        Enter scores
      </Link>
    </Card>
  );
}

function ShareCard({ funRoundId }: { funRoundId: UUID }) {
  const [copied, setCopied] = useState(false);
  const link = `${window.location.origin}/r/${funRoundId}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <Card>
      <h2>Invite your mates</h2>
      <p className="muted small">
        Send them this link — they tap it, sign in, and they&rsquo;re in.
      </p>
      <button type="button" onClick={() => void copy()}>
        {copied ? 'Copied ✓' : 'Copy join link'}
      </button>
    </Card>
  );
}

function AddVirtual({ funRoundId, disabled }: { funRoundId: UUID; disabled: boolean }) {
  const addVirtual = useAddVirtualToFunRound(funRoundId);
  const [name, setName] = useState('');

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    addVirtual.mutate(name.trim(), { onSuccess: () => setName('') });
  }

  return (
    <Card>
      <h2>Add someone without the app</h2>
      <p className="muted small">You&rsquo;ll enter their scores for them.</p>
      <form onSubmit={onSubmit}>
        <input
          aria-label="Their name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Sam"
        />
        <button type="submit" disabled={addVirtual.isPending || disabled || !name.trim()}>
          {disabled ? 'Group is full' : addVirtual.isPending ? 'Adding…' : 'Add them'}
        </button>
      </form>
      <ErrorNote error={addVirtual.error} />
    </Card>
  );
}

function FieldList({ participants }: { participants: Participant[] }) {
  if (participants.length === 0) return <Empty>Nobody yet.</Empty>;
  return (
    <ul className="list plain">
      {participants.map((p) => (
        <li key={p.id}>
          <span className="list-name">{p.display_name}</span>
          {p.is_virtual && <span className="badge">No app</span>}
        </li>
      ))}
    </ul>
  );
}
