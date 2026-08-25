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
