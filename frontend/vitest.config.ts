import { defineConfig, mergeConfig } from 'vitest/config';

import viteConfig from './vite.config.ts';

// Separate from vite.config.ts because Vitest 4 no longer widens Vite's
// UserConfig with a `test` key — putting it there is a type error, not a warning.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
    },
  }),
);
