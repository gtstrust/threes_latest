/**
 * Accepting an invitation — the screen someone lands on from a shared link or a
 * scanned QR, before they are in anything.
 *
 * Deliberately thin: what you were invited to, who is running it, how many are
 * in, and one button. Who is playing stays private until you are one of them,
 * which is why this reads the invitation rather than the event.
 */

import { useNavigate } from 'react-router-dom';

import { Card, ErrorNote, Loading, Page } from '../../components/ui';
import { useAcceptInvitation, useJoinPreview } from '../../lib/queries';
import type { JoinPreview } from '../../lib/types';

export function JoinPage({ code }: { code: string }) {
  const navigate = useNavigate();
  const preview = useJoinPreview(code);
  const accept = useAcceptInvitation(code);

  if (preview.isPending) return <Loading what="Loading the invite" />;
  if (preview.error || !preview.data)
    return (
      <Page title="Invitation" back={{ to: '/', label: 'Home' }}>
        <ErrorNote error={preview.error} />
      </Page>
    );

  const invite = preview.data;

  function enter(target: JoinPreview) {
    void navigate(target.kind === 'fun_round' ? `/r/${target.id}` : `/t/${target.id}`);
  }

  return (
    <Page title={invite.name} back={{ to: '/', label: 'Home' }}>
      <Card>
        <h2>You&rsquo;re invited</h2>
        <p className="muted">
          {invite.host_name} is running {invite.kind === 'fun_round' ? 'a fun round' : 'this event'}{' '}
          — {invite.player_count} {invite.player_count === 1 ? 'player' : 'players'} in so far.
        </p>

        {invite.can_join ? (
          <button
            type="button"
            onClick={() => accept.mutate(undefined, { onSuccess: () => enter(invite) })}
            disabled={accept.isPending}
          >
            {accept.isPending ? 'Joining…' : "I'm in"}
          </button>
        ) : (
          <>
            <p className="muted small">{whyNot(invite)}</p>
            {/* Still offered: a player who is already in the field lands here
                when they reuse the link, and the way on is the event itself. */}
            <button type="button" className="ghost" onClick={() => enter(invite)}>
              Take a look anyway
            </button>
          </>
        )}
        <ErrorNote error={accept.error} />
      </Card>
    </Page>
  );
}

function whyNot(invite: JoinPreview): string {
  if (invite.kind === 'fun_round' && invite.status === 'REGISTRATION_OPEN')
    return 'The group is full — a fun round is up to four players.';
  if (invite.status === 'CREATED') return 'Joining hasn’t opened yet. Try again shortly.';
  if (invite.status === 'TOURNAMENT_COMPLETE') return 'This event has finished.';
  return 'Joining has closed — they’ve already started.';
}
