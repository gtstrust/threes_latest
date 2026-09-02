/**
 * Configuration, read once and validated loudly.
 *
 * Vite inlines `import.meta.env.VITE_*` at build time, so a missing value is a
 * broken deployment rather than a runtime outage you can fix with a restart —
 * which is exactly why it is worth failing here, at startup, with the name of
 * the variable, instead of somewhere deep in a fetch three screens later.
 */

type Env = {
  supabaseUrl: string;
  /**
   * The **publishable** key (`sb_publishable_…`), and only ever that one.
   *
   * This value ships to every browser that loads the app; treat it as public.
   * The secret key (`sb_secret_…`) belongs to the backend alone — with it, a
   * caller bypasses row level security entirely and can read the whole
   * database. It must never appear in this directory.
   */
  supabasePublishableKey: string;
  apiBaseUrl: string;
  /**
   * Whether to offer signing in with a password as well as a magic link.
   *
   * A temporary bypass. Supabase's built-in mail service allows two messages an
   * hour, which is fewer than a fourball, so while that is the sender nobody can
   * reliably get in by link. A password needs no inbox.
   *
   * Defaults to **on**, because it exists precisely for the situation where the
   * link does not arrive — a bypass that has to be switched on is no use to
   * somebody already locked out. Turning it off is the deliberate act, and the
   * thing to do once custom SMTP is configured.
   */
  passwordLoginEnabled: boolean;
};

function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `${name} is not set. Copy frontend/.env.example to frontend/.env and fill it in.`,
    );
  }
  return value;
}

function readEnv(): Env {
  const key = required(
    'VITE_SUPABASE_PUBLISHABLE_KEY',
    import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
  );

  // A secret key here would be a credential leak in a static asset, so refuse to
  // start rather than serve it. Cheap to check, and the failure it prevents is
  // not one you would notice until someone else did.
  if (key.startsWith('sb_secret_')) {
    throw new Error(
      'VITE_SUPABASE_PUBLISHABLE_KEY holds a secret key. The browser must only ever ' +
        'receive the publishable key; the secret one bypasses row level security.',
    );
  }

  return {
    supabaseUrl: required('VITE_SUPABASE_URL', import.meta.env.VITE_SUPABASE_URL),
    supabasePublishableKey: key,
    apiBaseUrl: required('VITE_API_BASE_URL', import.meta.env.VITE_API_BASE_URL),
    passwordLoginEnabled: enabled(import.meta.env.VITE_ENABLE_PASSWORD_LOGIN),
  };
}

/**
 * An optional switch, on unless it is explicitly turned off.
 *
 * Deliberately not `required()`: an unset value is the normal case, and a build
 * that has never heard of this variable must keep working. Only the two spellings
 * of "no" count, so a typo leaves the bypass on rather than silently removing the
 * only way in.
 */
function enabled(value: string | undefined): boolean {
  const normalised = value?.trim().toLowerCase();
  return normalised !== 'false' && normalised !== '0';
}

export const env = readEnv();
