---
name: production-site-replica
description: End-to-end workflow for rebuilding a provided website URL as a high-fidelity, production-grade local frontend project. Use when a user asks to clone, replicate, recreate, rebuild, productionize, refactor, or make a maintainable demo of a website or landing page, especially when the work requires visual research, screenshot baselines, resource audits, modern React/TypeScript/Vite/TanStack Router implementation, componentized UI reconstruction, asset archival, sample-data minimization, interaction parity, screenshot regression, and lint/build/test verification.
---

# Production Site Replica

## Operating Rules

- Treat the target URL as a visual and interaction reference, not as a production dependency.
- Confirm scope, delivery path, local run command, target pages, and acceptance criteria when they are missing or ambiguous.
- Ask or state the authorization boundary. If the target appears to be an unauthorized commercial or branded site, build only a local research/demo or style-similar implementation; avoid trademark misuse, proprietary copy, full data mirrors, and anything intended for confusing public release.
- Do not rely on original-site scrape directories, hashed build paths, whole CSS/JS bundles, cache folders, temporary downloads, CDN paths, or third-party runtime URLs.
- Preserve user-visible behavior and appearance. Replace implementation details with clean, editable project code.
- Keep the repository clean. Do not leave `dist`, generated screenshots, crawler output, temporary scripts, or unused downloaded assets in the final project.

## Default Stack

- Prefer React + TypeScript + Vite + TanStack Router.
- Use the target site's requirements to decide additions: headless UI primitives, animation libraries, icon libraries, font packages, image optimization tools, or WebGL libraries.
- For current library/API details, use current docs via available documentation tools or official sources.
- For WebGL/WebGPU/canvas/shader-heavy pages, use `web-shader-extractor` first to identify render surfaces, shaders, textures, uniforms, and replay constraints.

## Workflow

### 1. Confirm Target And Boundaries

- Record the URL, page list, viewport targets, destination directory, local demo command, and exact user expectations.
- Determine whether the request is exact authorized replication, internal research, or style-similar reconstruction.
- Define what must be pixel-close and what can be sampled or substituted.
- Create a short plan before major edits when the scope spans capture, rebuild, cleanup, and verification.

### 2. Capture Visual And Interaction Baselines

- Open the target URL in a browser.
- Capture desktop and mobile screenshots with fixed viewport, DPR, scroll position, and stable animation timing.
- Capture at least: first viewport, full page when useful, post-scroll state, mobile menu, hover/focus states, filters, search, pagination/load more, theme toggle, modal/popover, empty state, loading state, and any media or canvas state the user can perceive.
- Save baseline evidence outside the final project tree, for example under a task `work/` directory.
- Record DOM inventory, fonts, colors, image dimensions, responsive breakpoints, animations, network failures, console errors, and external runtime dependencies.

### 3. Audit Original Resources

- Inspect HTML, CSS, JS, fonts, images, icons, video, JSON, API calls, inline data, and external references.
- Separate content assets needed for the local demo from scrape residue:
  - keep: visible brand/hero/media assets, required fonts, icons, textures, representative data, and state assets;
  - remove: original build output, hashed framework directories, whole bundled CSS/JS, source maps, crawler cache, unused pages, unused media, temporary downloads, and duplicate files.
- For repeated content such as cards, portfolios, products, articles, reviews, cases, media libraries, and comments, keep the minimal sample set needed to reproduce structure and key interactions:
  - the exact default visible items;
  - enough extra items to exercise load more or pagination;
  - one or more representatives per visible filter/category/mode;
  - examples for search hits and search empty state when search exists;
  - examples for liked/favorite/bookmark states when present;
  - an empty-state path.
- Do not preserve a complete data mirror unless the user explicitly owns and requests it.

### 4. Build A Clean Production Project

- Create or refactor the destination as a normal editable frontend project.
- Use a clear structure:

```text
src/
  components/
  routes/
  styles/
  data/
  hooks/
  lib/
  types/
public/
  assets/
    brand/
    fonts/
    images/
    icons/
    effects/
```

- Re-home assets into project-owned semantic paths and names. Prefer meaningful names such as `hero-background.webp`, `card-analytics-preview.webp`, `brand-logo.svg`, not copied hash names.
- Keep one project-owned style entrypoint or a coherent token system. Do not import original whole-site CSS bundles.
- Configure routing, metadata, linting, formatting, typechecking, and build scripts.
- If creating a homepage replica, make the first route the actual usable page, not a marketing explanation of the project.

### 5. Reimplement Components And Interactions

- Rebuild with project-owned components, data, hooks, tokens, layout rules, breakpoints, and interaction state.
- Match user-visible details: typography, color, spacing, shadows, radius, card ratio, media crop, hover/focus states, easing, animation timing, scrolling behavior, sticky elements, mobile layout, and safe text fitting.
- Implement real state transitions for key UX: menus, filters, search, load more, pagination, modals, tabs, accordions, theme toggles, favorites, empty states, and loading states.
- Use proven libraries for domain logic or complex visuals when appropriate. Use Three.js or WebGL tools for 3D/canvas work rather than hand-rolling fragile rendering unless the site is simple.
- Avoid static screenshot-only pages unless the user explicitly asks for a non-interactive mockup.

### 6. Minimize And Clean

- After the page works, audit project references and delete unreferenced images, fonts, icons, video, JSON, data, and temporary files.
- Delete `dist`, crawler output, source-site mirrors, source maps, cache folders, old docs, experimental code, and downloaded bundles that are not part of the maintained source.
- Run the bundled static asset report when useful:

```bash
node /path/to/production-site-replica/scripts/static-asset-report.mjs /path/to/project --json
```

- Treat the script as an audit aid, not as a substitute for manual review. Patch it locally if the project has unusual asset conventions.
- Confirm that no final source imports or references original-site build directories such as `_astro`, `_next/static`, `assets/vendor`, hashed framework chunks, temporary cache paths, or absolute third-party site asset paths.

### 7. Verify

- Run the project commands, adapting to the package manager:

```bash
npm run format
npm run lint
npm run test
npm run build
```

- If a command does not exist, either add the appropriate script or state why it is unavailable.
- Use Playwright or an equivalent browser tool for smoke tests covering the key interactions identified in the baseline.
- Capture final desktop and mobile screenshots at the same viewport/DPR as the baseline.
- Compare baseline and final screenshots with a deterministic image diff when possible. Report mismatch ratio and inspect any visible differences.
- Also report:
  - public asset file count and size before/after cleanup;
  - retained sample data count and rationale;
  - console errors and failed network resources;
  - build output status;
  - whether `dist` and temporary artifacts were removed after verification.

### 8. Final Delivery

- Provide the local demo URL and project path.
- Summarize the component/style/data/asset structure.
- List validation results: format, lint, typecheck/test, build, browser smoke tests, screenshot regression.
- Include cleanup statistics and explicitly state that the project no longer depends on original scrape products, full content mirrors, whole CSS/JS bundles, caches, or third-party asset paths.
- Mention any remaining caveats, such as intentionally substituted copyrighted assets, nondeterministic animations, or out-of-scope pages.

## Acceptance Checklist

- The default viewport visually matches the baseline closely.
- Mobile and desktop layouts are both validated.
- User-perceived interactions work, not just static rendering.
- Repeated content is represented by a minimal sample set.
- Assets are semantic, project-owned, and referenced by source.
- Unused assets, original-site mirrors, temporary files, and build artifacts are absent.
- The project runs locally and builds from source.
- The final answer includes objective evidence rather than only qualitative claims.
