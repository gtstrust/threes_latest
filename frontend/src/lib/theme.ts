/**
 * Which theme the app wears, and who decided.
 *
 * Three preferences, but only two themes: `system` is not a third look, it is
 * the absence of a choice. That distinction is the whole feature —
 *
 *   - **System**: follow the phone, *and* keep the on-course screens bright.
 *     The player has expressed no opinion, so the app applies its own: a screen
 *     used standing on a green in direct sun is legible bright and washes out
 *     dark, whatever the phone is set to.
 *   - **Light / Dark**: honoured everywhere, scoring included. Once somebody has
 *     actually chosen, overriding them on two screens reads as a bug rather than
 *     as care.
 *
 * The preference resolves to `light` or `dark` here rather than in CSS, which is
 * what keeps the stylesheet to two token blocks instead of four. The on-course
 * exception is then one selector keyed on `data-theme-source`, so no component
 * needs to know any of this.
 *
 * Stored on the device, not the profile: it applies before there is a player to
 * read one from, and the phone you play on and the laptop you organise from are
 * used in different light anyway.
 */

export type ThemePreference = 'system' | 'light' | 'dark';
export type Theme = 'light' | 'dark';

/** Kept in step with the inline stamp in `index.html`, which runs before this module. */
const KEY = 'threes.theme';

const DARK_QUERY = '(prefers-color-scheme: dark)';

/** What the phone is set to, or dark when the browser will not say. */
export function systemTheme(): Theme {
  return window.matchMedia?.(DARK_QUERY).matches ? 'dark' : 'light';
}

/**
 * The stored preference, defaulting to `system`.
 *
 * Storage access is guarded for the same reason `referral.ts` guards it: this
 * runs on every boot, and Safari's private mode has historically thrown on
 * access. Losing a preference is survivable; failing to start is not.
 */
export function readPreference(): ThemePreference {
  try {
    const stored = window.localStorage?.getItem(KEY);
    return stored === 'light' || stored === 'dark' ? stored : 'system';
  } catch {
    return 'system';
  }
}

/** The theme a preference actually comes out as. */
export function resolve(preference: ThemePreference): Theme {
  return preference === 'system' ? systemTheme() : preference;
}

/**
 * Put a preference on the document.
 *
 * Two attributes, doing different jobs. `data-theme` is the resolved look;
 * `data-theme-source` says whether it was chosen, which is what the on-course
 * override keys off — absent it, CSS could not tell "dark because they asked"
 * from "dark because the phone is".
 */
export function applyTheme(preference: ThemePreference): void {
  const root = document.documentElement;
  const theme = resolve(preference);

  root.dataset.theme = theme;
  if (preference === 'system') root.dataset.themeSource = 'system';
  else delete root.dataset.themeSource;

  // So the browser's own chrome — and an installed PWA's — matches the page
  // rather than contradicting it.
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', theme === 'dark' ? '#0b0f0c' : '#ffffff');
}

/** Remember a preference and apply it. */
export function setPreference(preference: ThemePreference): void {
  try {
    if (preference === 'system') window.localStorage?.removeItem(KEY);
    else window.localStorage?.setItem(KEY, preference);
  } catch {
    // Unwritable storage costs them the preference on the next load, not now.
  }
  applyTheme(preference);
}

/**
 * Keep `system` tracking the phone while the app is open.
 *
 * Without this, somebody whose phone flips to dark at sunset — mid-round — keeps
 * the daytime theme until they reload, which on a PWA left open on a cart may be
 * never. Returns an unsubscribe for React's benefit.
 */
export function watchSystemTheme(onChange: () => void): () => void {
  const media = window.matchMedia?.(DARK_QUERY);
  if (!media) return () => {};

  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}
