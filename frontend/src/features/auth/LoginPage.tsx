/**
 * The first screen anyone sees, and the one most likely to be opened on 4G
 * standing on a tee. Plain HTML inputs on purpose: browser autofill, password
 * managers and the email keyboard all work for free, which is most of what makes
 * this bearable one-handed outdoors.
 */

import { useState, type FormEvent } from 'react';

import { sendMagicLink } from '../../lib/supabase';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSending(true);
    setError(null);
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
        <h1>Check your email</h1>
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
      <h1>Threes</h1>
      <p>Sign in with your email — no password to remember.</p>
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
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
