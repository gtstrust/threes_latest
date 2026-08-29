/**
 * Carrying a referral code across the magic-link round trip.
 *
 * This is the whole difficulty of referrals on a passwordless app. Somebody
 * arrives at `/?ref=MATE-8K2QF`, types their email, and leaves — the next thing
 * that happens is an email, opened possibly in a different tab, whose link points
 * at Supabase and then back at the app's redirect URL. The query string that
 * carried the code is long gone by the time there is a session to attribute.
 *
 * So the code is stashed the moment the page loads and read back when the profile
 * is provisioned. `localStorage` rather than `sessionStorage`, because the link
 * genuinely can open in a new tab and a session store would be empty there.
 *
 * **Storage is treated as optional.** Safari's private mode has historically
 * thrown on write, some embedded webviews disable it outright, and it is absent
 * in jsdom. This module runs inside sign-in, so an exception here would cost
 * somebody their login to save a piece of attribution — a bad trade. When
 * storage is unavailable the code is held in memory instead, which still works
 * for a sign-in completed in the same tab and simply loses the attribution
 * otherwise.
 */

const KEY = 'threes.referral';

/** The query parameter a shared referral link carries. */
export const REFERRAL_PARAM = 'ref';

/** Fallback when the browser has no usable storage. Lost on reload, unlike the real thing. */
let inMemory: string | null = null;

function store(code: string): void {
  inMemory = code;
  try {
    window.localStorage?.setItem(KEY, code);
  } catch {
    // Quota, private mode, or storage disabled. The in-memory copy stands.
  }
}

function read(): string | null {
  try {
    return window.localStorage?.getItem(KEY) ?? inMemory;
  } catch {
    return inMemory;
  }
}

function clear(): void {
  inMemory = null;
  try {
    window.localStorage?.removeItem(KEY);
  } catch {
    // Nothing to undo — the in-memory copy is already gone.
  }
}

/**
 * Stash `?ref=…` if the current URL has one, then take it out of the address bar.
 *
 * Removing it matters: left there, the code survives a refresh and rides along
 * on any link forwarded from this tab, carrying somebody else's attribution.
 */
export function captureReferral(): void {
  const url = new URL(window.location.href);
  const code = url.searchParams.get(REFERRAL_PARAM);
  if (!code) return;

  store(code);
  url.searchParams.delete(REFERRAL_PARAM);
  window.history.replaceState({}, '', url.toString());
}

/** The stashed code, consumed. Undefined when there was none. */
export function takeReferral(): string | undefined {
  const code = read();
  if (!code) return undefined;
  clear();
  return code;
}
