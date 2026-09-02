import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv, type Plugin } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

import { findEnvProblems } from './build-env.ts';

/**
 * Fail the build when the configuration it would inline is not there.
 *
 * `apply: 'build'` is load-bearing rather than tidiness. `vitest.config.ts`
 * imports this file, and `vite dev` reads it on every start — a check that ran
 * in either would make a missing `.env` break the test suite instead of the
 * thing it is actually about. Only a build bakes values into an artefact that
 * outlives the process, and only a build is worth stopping.
 *
 * `loadEnv` rather than `process.env` because it reads both: the `.env` files a
 * developer has locally, and the prefixed variables Cloudflare and GitHub
 * Actions inject. The guard should not care which one it is looking at.
 */
function requireEnv(): Plugin {
  return {
    name: 'threes:require-env',
    apply: 'build',
    config(_config, { mode }) {
      const problems = findEnvProblems(loadEnv(mode, process.cwd(), 'VITE_'));
      if (problems.length > 0) {
        throw new Error(
          [
            'Cannot build: the frontend configuration is incomplete.',
            ...problems.map((problem) => `  - ${problem}`),
            '',
            'Vite inlines VITE_* at build time, so building without them produces a',
            'bundle that throws before it renders. Locally: copy .env.example to .env.',
            'On Cloudflare: Workers & Pages -> the Worker -> Settings -> Build ->',
            'Variables and secrets. See docs/DEPLOYMENT.md section 2.',
          ].join('\n'),
        );
      }
    },
  };
}

export default defineConfig({
  // Pin the dev port and refuse to start if it is taken, rather than silently
  // moving to 5174. 5173 is the origin the backend's CORS_ORIGINS and Supabase's
  // redirect allow-list know about; a second dev server on another port loads but
  // cannot reach the API, which reads to a user as "Could not reach the server".
  server: { port: 5173, strictPort: true },
  plugins: [
    requireEnv(),
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      // Precache the shell only. Deliberately no runtime caching of API
      // responses: ADR-005 defers offline score sync to Phase 2, and a service
      // worker quietly serving a stale leaderboard would be worse than an honest
      // error — a player would trust a board that had stopped moving.
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        navigateFallbackDenylist: [/^\/api/],
      },
      manifest: {
        name: 'Threes — short-form golf',
        short_name: 'Threes',
        description: 'Play and score 3-hole competitions.',
        theme_color: '#0b0f0c',
        background_color: '#0b0f0c',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
    }),
  ],
});
