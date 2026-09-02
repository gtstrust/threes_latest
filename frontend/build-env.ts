/**
 * The configuration check, moved one step earlier than `src/lib/env.ts`.
 *
 * That module throws in the browser, which is the right place for it — but it is
 * the *last* place the mistake can be caught. Vite inlines `VITE_*` at build
 * time, so a build with nothing to inline still succeeds, still uploads, and
 * still serves a 200. The bundle it produces throws on its first line and paints
 * a blank page, and every check short of opening a console says the deploy
 * worked.
 *
 * That is exactly how `app.threes.golf` first went live. So the same rule runs
 * here too, against the build environment, where a failure stops the deploy
 * instead of shipping it. Kept pure and separate from `vite.config.ts` so it can
 * be tested without running a build.
 */

export const REQUIRED_ENV_VARS = [
  'VITE_SUPABASE_URL',
  'VITE_SUPABASE_PUBLISHABLE_KEY',
  'VITE_API_BASE_URL',
] as const;

/**
 * Everything wrong with a build environment, as messages fit to print.
 *
 * Returns all of them rather than the first: the three are set together, in one
 * dashboard form, and finding them one failed build at a time is three round
 * trips for one mistake.
 *
 * @param env - Candidate values, as `loadEnv` returns them.
 * @returns One message per problem; empty when the environment is usable.
 */
export function findEnvProblems(env: Record<string, string | undefined>): string[] {
  const problems = REQUIRED_ENV_VARS.filter((name) => !env[name]?.trim()).map(
    (name) => `${name} is not set.`,
  );

  // Mirrors src/lib/env.ts. Catching it there means the key has already been
  // compiled into a published asset — this is the first point at which refusing
  // still prevents the leak rather than merely reporting it.
  if (env.VITE_SUPABASE_PUBLISHABLE_KEY?.startsWith('sb_secret_')) {
    problems.push(
      'VITE_SUPABASE_PUBLISHABLE_KEY holds a secret key. Only the publishable key ' +
        'may be built into the bundle; the secret one bypasses row level security.',
    );
  }

  return problems;
}
