import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // 'autoUpdate' silently updates the SW in the background.
      // Switch to 'prompt' if you want to show a "New version available" toast.
      registerType: 'autoUpdate',

      // Include these assets in the precache manifest
      includeAssets: ['vitar-logo.png', 'icons/*.png', 'screenshots/*.png'],

      // Point at the manifest we maintain manually in /public
      manifest: false,

      workbox: {
        // Cache the app shell (JS/CSS chunks) with a stale-while-revalidate strategy
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],

        // Don't cache API calls — always go to the network for fresh data
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],

        runtimeCaching: [
          // App shell — cache first, refresh in background
          {
            urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts-cache',
              expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          // API calls — network first, fall back to cache for offline resilience
          {
            urlPattern: /^\/api\/.*/i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'vitar-api-cache',
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 5 }, // 5 min
              networkTimeoutSeconds: 10,
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },

      devOptions: {
        // Enable SW in dev so you can test offline behaviour with `vite dev`
        enabled: false,
        type: 'module',
      },
    }),
  ],

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },

  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },

  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
          query: ['@tanstack/react-query'],
          forms: ['react-hook-form', 'zod', '@hookform/resolvers'],
        },
      },
    },
  },
})
