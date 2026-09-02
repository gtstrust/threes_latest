/**
 * The other half of the magic-link round trip: what comes back when it fails.
 *
 * A link that has expired, been used already, or been followed by something that
 * is not the player returns to the app as fragment parameters —
 * `#error=access_denied&error_code=otp_expired&error_description=…` — and until
 * this existed nothing read them. `supabase-js` throws on that URL from inside
 * its constructor's `initialize().catch()`, which only debug-logs, so the person
 * holding the dead link landed back on the sign-in form with no explanation and
 * nothing in the console. Indistinguishable from never having clicked.
 *
 * Reading it here is safe from the effect rather than needing module-level
 * capture: on the error path the SDK throws in `_getSessionFromURL` *before* it
 * reaches the `window.location.hash = ''` on its success path, so the parameters
 * are still there when React mounts. That ordering is the SDK's, not ours, so
 * `callback-error.test.ts` pins the behaviour this depends on.
 */

const ERROR = 'error';
const ERROR_CODE = 'error_code';
const ERROR_DESCRIPTION = 'error_description';

const PARAMS = [ERROR, ERROR_CODE, ERROR_DESCRIPTION];

/**
 * Wording for the failures people actually hit.
 *
 * Supabase's own `error_description` is written for whoever is reading the
 * dashboard ("Email link is invalid or has expired"), and it does not say what to
 * do next. On a tee, in the sun, the only useful sentence names the fix.
 *
 * Keyed across both `error_code` and `error`. `error_code` is tried first because
 * it says *why* it failed, where `error` alone only says the server refused — a
 * link that has expired and one clicked twice both arrive as
 * `error=access_denied`, and only the code separates them. Supabase's own
 * description is preferred over a bare `error` match, since a description that is
 * present is more specific than the category; the `error` entry is the last thing
 * tried before giving up and saying nothing useful.
 */
const KNOWN: Record<string, string> = {
  otp_expired: 'That sign-in link has expired. Send yourself a new one below.',
  access_denied: 'That sign-in link has already been used. Send yourself a new one below.',
};

/**
 * Answered once per page load, then remembered.
 *
 * `undefined` means "not looked yet", which is why it is not just `null`. The
 * memo is what makes this safe to call during render: reading takes the error off
 * the URL, so a second unmemoised call would find nothing and report no error —
 * and React calls a lazy `useState` initialiser twice under StrictMode.
 */
let answer: string | null | undefined;

/**
 * The sign-in failure this page load carries, if any, clearing it from the URL.
 *
 * Cleared because it is a fact about one navigation, not about the address: left
 * in place, a refresh would resurrect an error the player has already dealt with.
 */
export function takeCallbackError(): string | null {
  if (answer === undefined) answer = read();
  return answer;
}

function read(): string | null {
  const url = new URL(window.location.href);
  const fragment = new URLSearchParams(url.hash.replace(/^#/, ''));

  // Supabase returns these in the fragment under the implicit flow, but reads
  // both itself; matching that costs one line and means a query-string variant
  // does not silently go unreported.
  const source = fragment.get(ERROR) || fragment.get(ERROR_CODE) ? fragment : url.searchParams;
  if (!source.get(ERROR) && !source.get(ERROR_CODE)) return null;

  const code = source.get(ERROR_CODE);
  const kind = source.get(ERROR);
  const message =
    (code && KNOWN[code]) ||
    source.get(ERROR_DESCRIPTION) ||
    (kind && KNOWN[kind]) ||
    'That sign-in link did not work. Send yourself a new one below.';

  clear(url, fragment);
  return message;
}

/** Strip the auth parameters, leaving anything else on the URL untouched. */
function clear(url: URL, fragment: URLSearchParams): void {
  for (const param of PARAMS) {
    url.searchParams.delete(param);
    fragment.delete(param);
  }
  const rest = fragment.toString();
  url.hash = rest ? `#${rest}` : '';
  window.history.replaceState({}, '', url.toString());
}
