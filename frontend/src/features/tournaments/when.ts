/**
 * Moving a tee time between the wire and a `<input type="datetime-local">`.
 *
 * The two speak different languages and neither says so. The API stores an
 * instant (`scheduled_at`, ISO 8601 with an offset); the input reads and writes
 * a *naive* local wall-clock string with no zone at all. Converting by hand in
 * a component is where an 8:30am tee time quietly becomes 6:30pm — and the
 * reminder then fires on the wrong day, which nobody notices until players
 * don't turn up.
 *
 * So both directions live here, together, with the arithmetic written out.
 */

/**
 * An instant from the API → the `YYYY-MM-DDTHH:mm` the input expects, in the
 * viewer's own timezone.
 *
 * `toISOString()` is deliberately not used: it converts to UTC, which is the
 * bug. The local getters are what put the organiser's own clock in the box.
 */
export function toLocalInput(iso: string | null): string {
  if (!iso) return '';
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return '';

  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}` +
    `T${pad(when.getHours())}:${pad(when.getMinutes())}`
  );
}

/**
 * The input's naive local string → an instant for the API.
 *
 * `new Date('2026-09-12T08:30')` — no zone — is interpreted as *local* time by
 * every current engine, which is exactly what is wanted here: the organiser
 * typed their own wall clock. `toISOString()` then carries it to UTC for the
 * wire. Empty means "no date", which the API takes as null and which leaves the
 * event out of the reminder sweep.
 */
export function toInstant(local: string): string | null {
  if (!local) return null;
  const when = new Date(local);
  return Number.isNaN(when.getTime()) ? null : when.toISOString();
}

/** `Sat 12 Sep, 8:30am` — how a tee time is said out loud, not how it is stored. */
export function readableWhen(iso: string | null): string | null {
  if (!iso) return null;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return null;

  const day = when.toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
  const time = when
    .toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
    .toLowerCase()
    .replace(' ', '');
  return `${day}, ${time}`;
}
