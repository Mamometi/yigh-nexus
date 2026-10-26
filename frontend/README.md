# YIGH Nexus — frontend

React + Vite + TypeScript. See the main [README](../README.md) for how to run the whole app.

- `npm run dev` — development server on http://localhost:5173 (proxies `/api` to the backend on port 8000)
- `npm run build` — builds `dist/`, which the backend serves at http://localhost:8000
- `npx playwright test` — click-through tests against a running app (`BASE_URL=http://localhost:8000 npx playwright test`)
