/**
 * How an organiser hands out an event: a short code, a link, and a QR.
 *
 * The code is the invitation rather than the event's id, which is what makes all
 * three possible — an id can't be read aloud on a tee, can't be printed at a size
 * anyone would retype, and can never be withdrawn once it's on a sign.
 */

import { useState } from 'react';

import { Card, ErrorNote } from '../../components/ui';
import { useRegenerateJoinCode } from '../../lib/queries';
import type { UUID } from '../../lib/types';
import { QrCode } from './QrCode';

/** Local, not exported: a second exported value here trips fast-refresh. */
function joinUrl(code: string): string {
  return `${window.location.origin}/join/${code}`;
}

export function InviteCard({
  code,
  blurb,
  /** Only a tournament can be revoked — a fun round is over in an hour. */
  tournamentId,
}: {
  code: string;
  blurb: string;
  tournamentId?: UUID;
}) {
  const [copied, setCopied] = useState(false);
  const link = joinUrl(code);

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused outright. The code is on screen and the
      // whole point is that it's short enough to read out, so this is survivable.
      setCopied(false);
    }
  }

  return (
    <Card>
      <h2>Invite players</h2>
      <p className="muted small">{blurb}</p>

      <p className="join-code">{code}</p>
      <QrCode text={link} label={`QR code for join code ${code}`} />

      <button type="button" onClick={() => void copy()}>
        {copied ? 'Copied ✓' : 'Copy join link'}
      </button>

      {tournamentId && <Revoke tournamentId={tournamentId} />}
    </Card>
  );
}

function Revoke({ tournamentId }: { tournamentId: UUID }) {
  const regenerate = useRegenerateJoinCode(tournamentId);
  const [confirming, setConfirming] = useState(false);

  return (
    <>
      {confirming ? (
        <>
          <p className="muted small">
            Anyone holding the old link or a printed QR will stop being able to join. People already
            in the field stay in.
          </p>
          <button
            type="button"
            onClick={() => regenerate.mutate(undefined, { onSuccess: () => setConfirming(false) })}
            disabled={regenerate.isPending}
          >
            {regenerate.isPending ? 'Replacing…' : 'Yes, replace it'}
          </button>
          <button type="button" className="ghost" onClick={() => setConfirming(false)}>
            Keep this one
          </button>
        </>
      ) : (
        <button type="button" className="ghost" onClick={() => setConfirming(true)}>
          Replace this link
        </button>
      )}
      <ErrorNote error={regenerate.error} />
    </>
  );
}
