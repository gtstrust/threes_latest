/**
 * The build-time half of the configuration guard.
 *
 * Worth testing on its own because CI can never exercise the failure: the
 * frontend workflow supplies all three values, so a guard that had quietly
 * stopped working would pass every run and only be found by another blank
 * deployment.
 */

import { describe, expect, it } from 'vitest';

import { findEnvProblems, REQUIRED_ENV_VARS } from './build-env.ts';

const VALID = {
  VITE_SUPABASE_URL: 'https://abc.supabase.co',
  VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_abc123',
  VITE_API_BASE_URL: 'https://threes-api.fly.dev',
};

describe('build environment', () => {
  it('passes a complete environment', () => {
    expect(findEnvProblems(VALID)).toEqual([]);
  });

  it.each(REQUIRED_ENV_VARS)('names %s when it is missing', (missing) => {
    const problems = findEnvProblems({ ...VALID, [missing]: undefined });

    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain(missing);
  });

  it('reports every missing variable at once', () => {
    // Three failed builds to find one misconfigured form is three too many.
    expect(findEnvProblems({})).toHaveLength(REQUIRED_ENV_VARS.length);
  });

  it('treats an empty or blank value as missing', () => {
    // A dashboard field saved with nothing in it is the likely shape of this
    // mistake, and Vite inlines an empty string as readily as a real one.
    expect(findEnvProblems({ ...VALID, VITE_API_BASE_URL: '  ' })).toEqual([
      'VITE_API_BASE_URL is not set.',
    ]);
  });

  it('refuses a secret key before it reaches the bundle', () => {
    const problems = findEnvProblems({
      ...VALID,
      VITE_SUPABASE_PUBLISHABLE_KEY: 'sb_secret_realkeymaterial',
    });

    expect(problems).toHaveLength(1);
    expect(problems[0]).toMatch(/secret key/i);
  });
});
