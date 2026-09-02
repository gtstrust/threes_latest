/**
 * One assertion, about a default rather than about our own logic.
 *
 * The whole callback path assumes the implicit flow: the session comes back in
 * the fragment, `detectSessionInUrl` consumes it, and there is no
 * `exchangeCodeForSession` anywhere in this codebase. That was previously left to
 * whatever `@supabase/supabase-js` defaulted to. If an upgrade flips that default
 * to PKCE, the link returns as `?code=` instead, the SDK throws inside an
 * internal `.catch()` that only debug-logs, and login stops working in production
 * with every test still green. This is the test that would go red instead.
 */

import { describe, expect, it, vi } from 'vitest';

const { createClient } = vi.hoisted(() => ({ createClient: vi.fn(() => ({ auth: {} })) }));

vi.mock('@supabase/supabase-js', () => ({ createClient }));

vi.mock('./env', () => ({
  env: {
    supabaseUrl: 'https://project.supabase.co',
    supabasePublishableKey: 'sb_publishable_test',
    apiBaseUrl: 'http://localhost:8000',
  },
}));

describe('the Supabase client', () => {
  it('is pinned to the implicit flow the callback path depends on', async () => {
    await import('./supabase');

    expect(createClient).toHaveBeenCalledWith(
      'https://project.supabase.co',
      'sb_publishable_test',
      expect.objectContaining({
        auth: expect.objectContaining({ flowType: 'implicit', detectSessionInUrl: true }),
      }),
    );
  });
});
