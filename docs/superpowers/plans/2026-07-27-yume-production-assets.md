# Yume Production Asset Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> During Task 2, use the imagegen skill only for concept sheets; all shipped pixels require the Aseprite cleanup and in-engine review gates below.

**Goal:** Replace the functional placeholder pack with a cohesive, AI-assisted production pack for the isometric Yume office without changing application code or the asset contract.

**Architecture:** Editable `.aseprite` and `.tmj` files are the source of truth. A deterministic export command produces PNG atlases, atlas JSON, and the office map under `asset-packs/default/`. The existing pack validator checks structure and semantics; visual checks compare representative browser screenshots. AI-generated images remain references, not runtime assets.

**Tech Stack:** Image generation for concepts, Aseprite 1.3+, Tiled 1.11+, Node.js 24, PNGJS, Vitest, Playwright, React/Phaser asset-pack contract.

## Global Constraints

- Execute after the core dashboard plan and its placeholder-pack acceptance tests pass.
- Preserve 64×32 isometric tiles, 32×48 character canvases, integer scaling, and nearest-neighbor rendering.
- Preserve every required room, anchor, animation key, and manifest field; the asset swap must require configuration only.
- Yume must remain visually distinct from scheduled and delegated workers at a 1× display scale.
- AI output is concept material. Redraw, align, palette-limit, and animate every shipped frame in Aseprite.
- Do not imitate a living artist, named game, or protected character. Record generation prompts and licenses.
- Keep `.aseprite`, `.tmj`, palette, and reference files in Git; exports must be reproducible.
- The user owns the aesthetic approval gates. Automation may reject invalid exports but may not silently approve artwork.
- A task is complete only after its verification passes, its focused commit is created, and `git push origin main` succeeds.
- Work directly on `main`; do not add CI/CD or GitHub Actions before the full v1 acceptance gate passes.

---

## Planned File Structure

```text
asset-packs/
├── default/
│   ├── atlases/{characters.json,characters.png,ui.json,ui.png}
│   ├── maps/office.json
│   ├── tiles/office.png
│   └── pack.json
└── placeholder/
docs/art/
├── asset-checklist.md
├── generation-log.md
├── references/{characters,office,ui}/
└── style-bible.md
art/
├── palettes/yume-office.gpl
├── characters/{yume,scheduled-worker,delegated-worker}.aseprite
├── environment/{office-tiles,furniture,setpieces}.aseprite
├── maps/office.tmj
└── ui/hud.aseprite
tools/
├── export-assets.mjs
└── validate-pixels.mjs
tests/
├── assets/default-pack.test.ts
└── e2e/visual-assets.spec.ts
```

### Task 1: Freeze the Visual Language and Export Contract

**Files:**
- Create: `docs/art/style-bible.md`
- Create: `docs/art/asset-checklist.md`
- Create: `docs/art/generation-log.md`
- Create: `art/palettes/yume-office.gpl`
- Create: `tests/assets/default-pack.test.ts`
- Create: `tools/validate-pixels.mjs`
- Modify: `Makefile`

**Interfaces:**
- Produces: a 24-color shared palette
- Produces: `make assets-export` and `make assets-validate`
- Enforces: exact frame names, dimensions, transparent backgrounds, and pack parity

- [ ] **Step 1: Write the style bible**

Record these fixed rules:

```md
- Projection: 2:1 isometric; one floor tile is 64×32 px.
- Characters: 32×48 px frame, feet centered at (16, 40).
- Directions: south-west and south-east are authored; north-facing motion may
  mirror only when clothing and carried props remain correct.
- Palette: 24 shared colors plus transparency; no alpha-smoothed edges.
- Light: warm top-left key light; cool lower-right shadow.
- Outline: one-pixel colored outline, never pure black except UI text shadow.
- Priority: readable silhouette, role color, state prop, then facial detail.
- Tone: cozy near-future office; original design, no direct franchise motifs.
```

The checklist must enumerate every sprite, animation, tile family, setpiece, UI element, and required review screenshot.

- [ ] **Step 2: Add a failing production-pack contract test**

Run: `pnpm add -Dw vitest`

```ts
import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";

const requiredAnimations = [
  "yume-idle-sw", "yume-walk-sw", "yume-work-sw", "yume-think-sw",
  "worker-idle-sw", "worker-walk-sw", "worker-work-sw",
  "worker-enter-sw", "worker-exit-sw", "worker-failed-sw",
];
const requiredAnchors = [
  "ceo", "memory", "research", "work", "automation", "lobby",
];

describe("default production pack", () => {
  it("preserves the placeholder pack contract", async () => {
    const pack = JSON.parse(await readFile("asset-packs/default/pack.json", "utf8"));
    expect(pack.schema_version).toBe(1);
    expect(pack.id).toBe("default");
    expect(pack.tile).toEqual({ width: 64, height: 32 });
    expect(pack.character).toEqual({ width: 32, height: 48 });
    expect(Object.keys(pack.animations)).toEqual(expect.arrayContaining(requiredAnimations));
    expect(Object.keys(pack.anchors)).toEqual(expect.arrayContaining(requiredAnchors));
  });
});
```

- [ ] **Step 3: Run the test and verify failure**

Run: `pnpm vitest run tests/assets/default-pack.test.ts`

Expected: FAIL because `asset-packs/default/pack.json` does not exist.

- [ ] **Step 4: Implement pixel-level validation**

`tools/validate-pixels.mjs` must read PNGs with PNGJS and fail when:

```js
const constraints = {
  paletteMaximum: 24,
  characterFrame: [32, 48],
  tile: [64, 32],
  allowedAlpha: new Set([0, 255]),
};
```

Implement the checks directly:

```js
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { PNG } from "pngjs";

const root = process.argv[2];
if (!root) throw new Error("usage: validate-pixels.mjs ASSET_PACK");
const pack = JSON.parse(await readFile(join(root, "pack.json"), "utf8"));
const paletteText = await readFile("art/palettes/yume-office.gpl", "utf8");
const palette = new Set(
  paletteText.split("\n")
    .filter((line) => /^\s*\d+\s+\d+\s+\d+/.test(line))
    .map((line) => line.trim().split(/\s+/).slice(0, 3).join(",")),
);
const atlas = PNG.sync.read(await readFile(join(root, pack.atlas.replace(".json", ".png"))));
if (atlas.width % pack.character.width || atlas.height % pack.character.height) {
  throw new Error("character atlas does not divide into declared frames");
}
const frameCount =
  (atlas.width / pack.character.width) * (atlas.height / pack.character.height);
for (const [name, frames] of Object.entries(pack.animations)) {
  if (frames.length === 0 || frames.some((frame) => frame < 0 || frame >= frameCount)) {
    throw new Error(`animation ${name} contains an invalid frame`);
  }
}
const colors = new Set();
for (let offset = 0; offset < atlas.data.length; offset += 4) {
  const alpha = atlas.data[offset + 3];
  if (!constraints.allowedAlpha.has(alpha)) throw new Error("non-binary alpha");
  if (alpha === 255) {
    colors.add(`${atlas.data[offset]},${atlas.data[offset + 1]},${atlas.data[offset + 2]}`);
  }
}
if (colors.size > constraints.paletteMaximum) {
  throw new Error(`palette has ${colors.size} colors; maximum is 24`);
}
for (const color of colors) {
  if (!palette.has(color)) throw new Error(`color ${color} is outside the committed palette`);
}
const map = JSON.parse(await readFile(join(root, pack.map), "utf8"));
if (
  map.orientation !== "isometric" ||
  map.tilewidth !== constraints.tile[0] ||
  map.tileheight !== constraints.tile[1]
) {
  throw new Error("map must use 64x32 isometric tiles");
}
const floor = map.layers.find((layer) => layer.name === "floor");
for (const [name, anchor] of Object.entries(pack.anchors)) {
  const index = anchor.y * map.width + anchor.x;
  if (!floor || floor.data[index] === 0) throw new Error(`${name} anchor is not walkable`);
}
```

- [ ] **Step 5: Add deterministic commands**

```make
.PHONY: assets-export assets-validate

assets-export:
	node tools/export-assets.mjs

assets-validate:
	uv run --package yume-api python -m yume_api.assets.validator asset-packs/default
	node tools/validate-pixels.mjs asset-packs/default
	pnpm vitest run tests/assets/default-pack.test.ts
```

- [ ] **Step 6: Verify documentation and commit**

Run: `test -s docs/art/style-bible.md && test -s docs/art/asset-checklist.md`

```bash
git add docs/art art/palettes tests/assets tools/validate-pixels.mjs Makefile
git commit -m "docs: define production asset language"
```

### Task 2: Generate and Select Original Concept Boards

**Files:**
- Create: `docs/art/references/characters/*.png`
- Create: `docs/art/references/office/*.png`
- Create: `docs/art/references/ui/*.png`
- Modify: `docs/art/generation-log.md`
- Modify: `docs/art/style-bible.md`

**Interfaces:**
- Consumes: the frozen style bible
- Produces: approved character, environment, and UI reference boards

- [ ] **Step 1: Generate the character board with the imagegen skill**

Use this prompt as the base, adding the style-bible palette image as a reference when supported:

```text
Original pixel-art concept board for a cozy near-future isometric personal
assistant office. Show three clearly distinct roles: Yume, a confident CEO with
a warm violet and gold identity; a persistent scheduled worker with teal
calendar motifs; and an ephemeral delegated worker with blue utility clothing.
Include front three-quarter silhouettes, two walk poses, desk-work props, and
small expression studies. Crisp hard-edged pixels, limited 24-color palette,
no anti-aliasing, neutral background, design sheet only. Do not reference or
imitate any existing game, franchise, artist, or character.
```

Save the unedited result under `docs/art/references/characters/` and record the date, tool, full prompt, output filename, and selection notes in `generation-log.md`.

- [ ] **Step 2: Generate the office and UI boards**

Create one office board covering the six approved zones and one UI board covering a thin border HUD, task panel, connection badge, and compact agent inspector. Explicitly request a 2:1 isometric projection, 64×32 tile logic, original motifs, hard pixel edges, and the same palette. Save and log every result.

- [ ] **Step 3: Run the human selection gate**

The user chooses:

- one silhouette for each role;
- one office material/light direction;
- one motif for each of the six rooms;
- one border, panel, icon, and typography direction.

Record `accepted`, `rejected`, and concrete cleanup notes beside each board. No runtime asset work begins until all four choices are marked `accepted`.

- [ ] **Step 4: Convert selections into measurable rules**

Update `style-bible.md` with role color assignments, silhouette notes, furniture proportions, wall height, UI corner treatment, and example hex values mapped to palette indexes. Avoid prose such as “make it feel polished”; every note must describe a visible decision.

- [ ] **Step 5: Commit concept provenance**

```bash
git add docs/art
git commit -m "art: select original dashboard concepts"
```

### Task 3: Author and Export the Character Atlases

**Files:**
- Create: `art/characters/yume.aseprite`
- Create: `art/characters/scheduled-worker.aseprite`
- Create: `art/characters/delegated-worker.aseprite`
- Create: `tools/export-assets.mjs`
- Create: `asset-packs/default/atlases/characters.png`
- Create: `asset-packs/default/atlases/characters.json`
- Create: `asset-packs/default/pack.json`
- Modify: `docs/art/asset-checklist.md`

**Interfaces:**
- Produces: character animations named by `{role}-{state}-{direction}`
- Preserves: feet origin `(16, 40)` across all frames

- [ ] **Step 1: Draw and clean Yume**

Create a 32×48 Aseprite file using only the committed palette. Author these tagged animations:

| Tag | Frames | Timing |
|---|---:|---:|
| `idle-sw` | 4 | 240 ms |
| `walk-sw` | 8 | 100 ms |
| `think-sw` | 4 | 180 ms |
| `work-sw` | 6 | 120 ms |
| `waiting-sw` | 4 | 200 ms |
| `success-sw` | 6 | 100 ms |
| `failed-sw` | 4 | 180 ms |

Keep feet fixed at `(16, 40)` for idle/work frames and align walk contact frames to the same baseline. Create approved south-east variants by authored redraw or safe horizontal mirroring.

- [ ] **Step 2: Draw worker sources**

Give both worker types the same frame canvas and locomotion timing. Scheduled workers retain their role motif at 1×; delegated workers include distinct `enter-sw` and `exit-sw` tags. Role variation is palette-based, not separate unbounded character files.

- [ ] **Step 3: Implement deterministic Aseprite export**

`tools/export-assets.mjs` invokes Aseprite once per source and merges its JSON-array output into one stable atlas:

```js
const sources = [
  ["yume", "art/characters/yume.aseprite"],
  ["scheduled", "art/characters/scheduled-worker.aseprite"],
  ["worker", "art/characters/delegated-worker.aseprite"],
];
const aseprite = process.env.ASEPRITE_BIN ?? "/Applications/Aseprite.app/Contents/MacOS/aseprite";
```

Each invocation uses:

```text
--batch SOURCE --list-tags --trim-sprite
--sheet OUTPUT.png --data OUTPUT.json --format json-array
--filename-format {title}-{tag}-{frame}
```

The merge stage restores each trimmed frame to a 32×48 logical frame, sorts keys lexically, writes relative paths only, and rejects a changed tag or frame count.

- [ ] **Step 4: Add the initial production manifest**

Copy the placeholder manifest structure, set `id` to `default`, change only atlas paths and display metadata, and retain the exact animation aliases and six anchors. Do not change dashboard code.

- [ ] **Step 5: Export and validate**

Run:

```bash
make assets-export
make assets-validate
find asset-packs/default -type f -print0 | sort -z | xargs -0 shasum -a 256 > /tmp/yume-assets.before
make assets-export
find asset-packs/default -type f -print0 | sort -z | xargs -0 shasum -a 256 > /tmp/yume-assets.after
diff -u /tmp/yume-assets.before /tmp/yume-assets.after
```

Expected: the second export produces no diff and all contract/pixel tests pass.

- [ ] **Step 6: Review in the running dashboard**

Capture screenshots of Yume and both worker classes at 1× and 2× while idle, walking, working, waiting, succeeding, failing, entering, and exiting. Reject any frame with foot sliding, clipped props, ambiguous roles, or subpixel blur; fix the `.aseprite` source and re-export.

- [ ] **Step 7: Commit**

```bash
git add art/characters asset-packs/default tools/export-assets.mjs docs/art/asset-checklist.md
git commit -m "art: add production character atlases"
```

### Task 4: Build the Six-Zone Isometric Office

**Files:**
- Create: `art/environment/office-tiles.aseprite`
- Create: `art/environment/furniture.aseprite`
- Create: `art/environment/setpieces.aseprite`
- Create: `art/maps/office.tmj`
- Create: `asset-packs/default/tiles/office.png`
- Create: `asset-packs/default/maps/office.json`
- Modify: `tools/export-assets.mjs`
- Modify: `docs/art/asset-checklist.md`

**Interfaces:**
- Produces: Tiled layers `floor`, `walls`, `furniture-low`, `actors`, `furniture-high`, `lighting`
- Produces: walkable grid and named anchors for all six zones

- [ ] **Step 1: Author the reusable tile families**

Draw complete 64×32 floor diamonds, wall segments, doors, shadows, and transitions. Add furniture footprints on the isometric grid. Every object that can cover an actor must declare its pixel-space depth baseline.

- [ ] **Step 2: Draw one readable setpiece per room**

Use these fixed motifs:

| Room | Required visual anchor |
|---|---|
| CEO | Yume’s desk and status display |
| Memory | secured archive vault |
| Research | library shelves and research terminal |
| Work | clustered employee desks |
| Automation | scheduler wall and machine bay |
| Lobby | entrance portal and arrival marker |

The room must remain identifiable without text labels at the default fitted-camera scale.

- [ ] **Step 3: Assemble the final Tiled map**

Create an isometric `.tmj` with the fixed layer order and logical tile coordinates. Add object layers named `anchors`, `walkable`, and `depth`. Anchor objects use the exact IDs `ceo`, `memory`, `research`, `work`, `automation`, and `lobby`; every anchor must be inside one connected walkable component.

- [ ] **Step 4: Export map and tiles**

Extend `tools/export-assets.mjs` to:

1. export the three environment sources;
2. copy and normalize `office.tmj` into `asset-packs/default/maps/office.json`;
3. remove editor-only absolute paths;
4. sort properties and object arrays by name;
5. reject external files outside `asset-packs/default`.

- [ ] **Step 5: Validate pathing and depth**

Run:

```bash
make assets-export
make assets-validate
pnpm --dir apps/web test --run src/game/paths.test.ts
```

In the dashboard, dispatch one worker to each room, verify it never crosses a wall or furniture footprint, and verify actors render behind `furniture-high` at the correct baseline.

- [ ] **Step 6: Commit**

```bash
git add art/environment art/maps asset-packs/default tools/export-assets.mjs docs/art/asset-checklist.md
git commit -m "art: build production isometric office"
```

### Task 5: Author the Pixel UI Pack

**Files:**
- Create: `art/ui/hud.aseprite`
- Create: `asset-packs/default/atlases/ui.png`
- Create: `asset-packs/default/atlases/ui.json`
- Modify: `asset-packs/default/pack.json`
- Modify: `apps/web/src/app/app.css`
- Modify: `apps/web/src/ui/Hud.tsx`
- Modify: `apps/web/src/ui/AgentInspector.tsx`
- Modify: `apps/web/src/ui/ChatPanel.tsx`
- Modify: `tools/export-assets.mjs`

**Interfaces:**
- Produces: nine-slice frames, state icons, role badges, pointer, and selection marker
- Preserves: accessible HTML controls and text

- [ ] **Step 1: Draw UI sprites**

Author atlas tags for `panel-corners`, `panel-edges`, `connection-*`, `status-*`, `role-*`, `selection-ring`, and `pointer`. Use nine-slice borders so panels can resize without scaling corners.

- [ ] **Step 2: Export UI atlas metadata**

Add `hud.aseprite` to the deterministic export list. Record each nine-slice inset in `pack.json`; validate that opposing insets leave a positive stretchable center.

- [ ] **Step 3: Apply artwork without rasterizing semantics**

Use CSS border-image or layered background slices for chrome. Keep task input, buttons, agent labels, error messages, focus rings, and live regions as HTML. Add `image-rendering: pixelated`; scale pixel sprites only by whole-number CSS custom properties.

- [ ] **Step 4: Verify interaction and accessibility**

Run:

```bash
pnpm --dir apps/web test --run
pnpm --dir apps/web typecheck
pnpm e2e --grep "task panel|agent inspector|keyboard"
```

At 1440×900 and 390×844, confirm that the map remains dominant, panels do not overlap the selected agent, all controls remain keyboard reachable, and text meets WCAG AA contrast.

- [ ] **Step 5: Commit**

```bash
git add art/ui asset-packs/default apps/web/src tools/export-assets.mjs
git commit -m "art: add production pixel interface"
```

### Task 6: Make Production the Default and Complete Visual QA

**Files:**
- Modify: `config/dashboard.example.yaml`
- Modify: `compose.yaml`
- Modify: `tests/e2e/visual-assets.spec.ts`
- Create: `tests/e2e/screenshots/.gitkeep`
- Create: `asset-packs/default/LICENSE.md`
- Modify: `README.md`
- Modify: `docs/art/asset-checklist.md`

**Interfaces:**
- Changes default configuration from `placeholder` to `default`
- Retains `YUME_ASSET_PACK=placeholder` as a diagnostic fallback

- [ ] **Step 1: Add failing visual-state coverage**

```ts
for (const state of ["idle", "walking", "working", "waiting", "failed"]) {
  test(`production pack renders ${state}`, async ({ page }) => {
    await page.goto(`/?fixture=${state}`);
    await expect(page.getByTestId("office-canvas")).toHaveScreenshot(
      `production-${state}.png`,
      { animations: "disabled", maxDiffPixelRatio: 0.01 },
    );
  });
}
```

Run: `pnpm e2e --grep "production pack renders"`

Expected: FAIL until approved screenshot baselines are captured.

- [ ] **Step 2: Approve deterministic baselines**

Run the fake Hermes fixture with a fixed clock, viewport, device scale factor, and event order. Capture baselines only after the user approves the six-room overview plus idle, walking, working, waiting, and failure states. Never update snapshots merely to make tests pass.

- [ ] **Step 3: Switch the default pack**

Set `asset_pack: default` in the example configuration and `YUME_ASSET_PACK=default` in Compose. Verify that setting `YUME_ASSET_PACK=placeholder` still boots without any source-code changes.

- [ ] **Step 4: Record asset rights and customization workflow**

`asset-packs/default/LICENSE.md` identifies the project license for hand-authored exports and lists AI-generated reference provenance without claiming third-party ownership. `README.md` explains how to copy a pack, edit source files manually, export, validate, and select it through configuration.

- [ ] **Step 5: Run the release gate**

Run:

```bash
make assets-export
make assets-validate
make lint
make test
make build
pnpm e2e
docker compose build
docker compose up -d
curl --fail http://127.0.0.1:8000/api/health
docker compose down
git diff --check
```

Expected: every command exits 0, a clean re-export leaves no diff, and both production and placeholder packs load.

- [ ] **Step 6: Perform the final human visual gate**

At desktop and phone viewports, approve:

- instant role recognition for Yume, scheduled workers, and delegated workers;
- readable activity in all six rooms;
- clean entry, traversal, task, completion, failure, and exit animations;
- no pixel shimmer, foot sliding, clipping, broken depth, or non-integer scaling;
- unobstructed task panel and inspector;
- coherent palette and lighting across characters, office, and UI.

Mark every row in `asset-checklist.md` with the reviewer and date.

- [ ] **Step 7: Commit**

```bash
git add asset-packs/default config compose.yaml tests/e2e README.md docs/art/asset-checklist.md
git commit -m "feat: ship production asset pack"
```

## Completion Gate

The production asset plan is complete only when:

1. `make assets-export` is deterministic and `make assets-validate` passes.
2. The default and placeholder packs both satisfy the same manifest contract.
3. The full automated suite, Docker smoke test, and approved visual baselines pass.
4. Every shipped frame has been cleaned in Aseprite and reviewed in Phaser at 1×.
5. Asset provenance, license, manual customization, and rollback instructions are documented.
