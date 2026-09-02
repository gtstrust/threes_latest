/**
 * The first screen anyone sees, and the one most likely to be opened on 4G
 * standing on a tee. Plain HTML inputs on purpose: browser autofill, password
 * managers and the email keyboard all work for free, which is most of what makes
 * this bearable one-handed outdoors.
 */

import { useState, type FormEvent } from 'react';

import { sendMagicLink } from '../../lib/supabase';

/**
 * `notice` is why the last attempt failed — an expired or already-used link.
 * It arrives from the URL rather than from this form, so it is shown until the
 * next submit replaces it with whatever that attempt produces.
 */
export function LoginPage({ notice }: { notice?: string | null } = {}) {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const message = error ?? (dismissed ? null : (notice ?? null));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSending(true);
    setError(null);
    // The old link's failure stops being the news the moment they ask for a new
    // one; whatever this attempt does is.
    setDismissed(true);
    try {
      // Back to wherever they started, so a link shared into a group chat lands
      // people on the tournament rather than on a generic home screen.
      await sendMagicLink(email, `${window.location.origin}${window.location.pathname}`);
      setSent(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not send the link.');
    } finally {
      setSending(false);
    }
  }

  if (sent) {
    return (
      <main className="centred">
        <Wordmark />
        <h1 className="hero-title">Check your email</h1>
        <p>
          We sent a sign-in link to <strong>{email}</strong>. Open it on this device.
        </p>
        <button type="button" onClick={() => setSent(false)}>
          Use a different address
        </button>
      </main>
    );
  }

  return (
    <main className="centred">
      <Wordmark />
      <h1 className="hero-title">
        Three holes.
        <br />
        One match.
      </h1>
      <p className="muted">Sign in with your email — no password to remember.</p>
      <form onSubmit={onSubmit}>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="email"
          autoFocus
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
        />
        <button type="submit" disabled={sending || !email}>
          {sending ? 'Sending…' : 'Send me a link'}
        </button>
      </form>
      {message && <p role="alert">{message}</p>}
      <p className="muted small">We&rsquo;ll email you a link that signs you in on this device.</p>
    </main>
  );
}

/**
 * The mark: a ball's dimples read as three, which is the format.
 *
 * Inline SVG rather than a file — it is nine elements, it inherits `currentColor`
 * so it follows the theme without a second asset, and it costs no request on the
 * one screen where first paint over 4G actually matters.
 */
function Wordmark() {
  return (
    <p className="wordmark">
      <svg width="30" height="30" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
        <circle cx="12" cy="8.4" r="1.5" fill="currentColor" />
        <circle cx="8.9" cy="13.8" r="1.5" fill="currentColor" />
        <circle cx="15.1" cy="13.8" r="1.5" fill="currentColor" />
      </svg>
      <span>Threes</span>
    </p>
  );
}
