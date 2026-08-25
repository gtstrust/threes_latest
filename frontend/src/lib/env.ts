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
  };
}

export const env = readEnv();
