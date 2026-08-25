import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
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
        theme_color: '#1b5e20',
        background_color: '#ffffff',
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
