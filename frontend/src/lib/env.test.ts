/**
 * The startup guard on configuration.
 *
 * The important case is the last one. Everything in this directory is compiled
 * into a static asset that any visitor can read, so a secret key placed here is
 * a published credential — and one that bypasses row level security entirely.
 * Refusing to boot is the cheapest possible failure; the alternative is not
 * noticing until somebody else does.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

const VALID = {
  VITE_SUPABASE_URL: 'https://abc.supabase.co',
  VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_abc123',
  VITE_API_BASE_URL: 'http://localhost:8000',
};

async function loadEnv(overrides: Partial<Record<string, string | undefined>>) {
  vi.resetModules();
  vi.stubEnv('VITE_SUPABASE_URL', '');
  for (const [key, value] of Object.entries({ ...VALID, ...overrides })) {
    vi.stubEnv(key, value ?? '');
  }
  return import('./env');
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe('configuration', () => {
  it('reads a complete configuration', async () => {
    const { env } = await loadEnv({});

    expect(env.supabaseUrl).toBe('https://abc.supabase.co');
    expect(env.apiBaseUrl).toBe('http://localhost:8000');
  });

  it.each([
    ['VITE_SUPABASE_URL'],
    ['VITE_SUPABASE_PUBLISHABLE_KEY'],
    ['VITE_API_BASE_URL'],
  ])('refuses to start without %s, naming it', async (missing) => {
    // Vite inlines these at build time, so a missing one is a broken deployment
    // rather than something a restart fixes. Naming it here beats a null
    // dereference three screens later.
    await expect(loadEnv({ [missing]: undefined })).rejects.toThrow(missing);
  });

  it('refuses a secret key in the browser bundle', async () => {
    await expect(
      loadEnv({ VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_secret_realkeymaterial' }),
    ).rejects.toThrow(/secret key/i);
  });
});

describe('the password login flag', () => {
  it('is on when unset, because it exists for people already locked out', async () => {
    const { env } = await loadEnv({ VITE_ENABLE_PASSWORD_LOGIN: undefined });

    expect(env.passwordLoginEnabled).toBe(true);
  });

  it.each([['false'], ['0'], ['FALSE'], [' false ']])('is off for %o', async (value) => {
    const { env } = await loadEnv({ VITE_ENABLE_PASSWORD_LOGIN: value });

    expect(env.passwordLoginEnabled).toBe(false);
  });

  it.each([['true'], ['1'], ['yes'], ['flase']])('stays on for %o', async (value) => {
    // Including the typo deliberately: this is the only way into the app while
    // magic links are not arriving, so a misspelt "false" must not silently
    // remove it. Off has to be spelled correctly to count.
    const { env } = await loadEnv({ VITE_ENABLE_PASSWORD_LOGIN: value });

    expect(env.passwordLoginEnabled).toBe(true);
  });
});
