/**
 * Your own referral link, and what it has brought in.
 *
 * Attribution, not a reward — there is nothing to claim here. The count answers
 * "is word of mouth working?", which is worth being able to ask before there is
 * revenue to fund a reward for it, and before an incentive collides with the
 * organiser fee Phase 3 has yet to design.
 *
 * Shares the copy-and-QR treatment of an event invitation because it is the same
 * gesture — a short code somebody passes to somebody else — and a second visual
 * language for it would only make both harder to recognise.
 */

import { useState } from 'react';

import { Card, ErrorNote, Loading } from '../../components/ui';
import { useMyReferrals } from '../../lib/queries';
import { QrCode } from '../invite/QrCode';

export function ReferralCard() {
  const referrals = useMyReferrals();
  const [copied, setCopied] = useState(false);

  if (referrals.isPending) return <Loading what="Loading your link" />;
  if (referrals.error || !referrals.data)
    return (
      <Card>
        <h2>Bring a mate</h2>
        <ErrorNote error={referrals.error} />
      </Card>
    );

  const { referral_code, players_referred } = referrals.data;
  const link = `${window.location.origin}/?ref=${referral_code}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Refused clipboard access is survivable — the code is on screen, and it
      // is short enough to read out, which is what the alphabet is chosen for.
      setCopied(false);
    }
  }

  return (
    <Card>
      <h2>Bring a mate</h2>
      <p className="muted small">
        {players_referred === 0
          ? 'Send this to someone who hasn’t played Threes. They sign up through it and you’ll see them here.'
          : `${players_referred} ${players_referred === 1 ? 'player has' : 'players have'} joined through your link.`}
      </p>

      <p className="join-code">{referral_code}</p>
      <QrCode text={link} label={`QR code for referral code ${referral_code}`} />

      <button type="button" onClick={() => void copy()}>
        {copied ? 'Copied ✓' : 'Copy your link'}
      </button>
    </Card>
  );
}
