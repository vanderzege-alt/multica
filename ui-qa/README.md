# Multica UI QA adapter

This repository owns a Next.js web app, an Electron desktop app, and an Expo/React Native iOS app. This adapter covers the public marketing homepage only. Desktop and iOS remain mapped to their existing runners and are not claimed as covered by browser emulation.

## Commands

- `pnpm ui:preview` starts `@multica/web` on `http://localhost:3100`, waits for `/`, writes preview readiness evidence, and stays in the foreground.
- `pnpm ui:screenshots` captures screenshots for the declared target.
- `pnpm ui:a11y` runs axe-core on that visible state.
- `pnpm ui:visual` compares against committed, reviewed baselines.
- `pnpm ui:baseline:update` explicitly proposes a baseline update. Review each image before committing it.

On Linux (CI), all four Playwright projects run: Chromium, Firefox, WebKit desktop, and WebKit iPhone emulation. On macOS/Windows, the standard commands use Chromium for a timely local run; set `UI_ALL_BROWSERS=1` to opt into every configured project. Screenshot baselines are OS-specific. The committed `*-linux.png` baselines are captured in the pinned Linux Playwright image and visually reviewed; local Darwin baselines are evidence only and are not committed.

The `/` target asserts the public marketing headline and download action, mocks `/api/` and `/auth/` requests, and blocks external font/image requests so the preview uses no real service, account, or user data. The runner records commit, build ID, runtime, OS, browser, viewport, route/state, checks, and artifact paths in `ui-qa-artifacts/manifest.json`, which CI attaches to the exact tested commit.

## Review and limits

CI never updates snapshots. `.github/workflows/ui-qa-baselines.yml` is manual and uploads a proposal artifact; it does not commit files. Review actual/diff images and update baselines in a separate change. Axe checks only rendered DOM; activate other states and perform keyboard, focus, zoom, and screen-reader review separately. The iPhone project is browser emulation, not native iOS execution.
