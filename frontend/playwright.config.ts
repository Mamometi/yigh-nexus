import { defineConfig } from '@playwright/test'

// Runs against an already-running app: API + Vite dev server.
// BASE_URL defaults to the Vite dev server (which proxies /api to FastAPI).
export default defineConfig({
  testDir: './e2e', testIgnore: '**/_old/**',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL: process.env.BASE_URL ?? 'http://localhost:5180', viewport: { width: 1440, height: 1000 } },
})
