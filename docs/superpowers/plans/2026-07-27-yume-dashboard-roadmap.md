# Yume Dashboard Implementation Roadmap

The approved design is split into three execution plans so each deliverable remains independently reviewable and testable.

1. [Core Dashboard](./2026-07-27-yume-dashboard-core.md) — monorepo foundation, contracts, placeholder asset pack, Hermes adapter, FastAPI event service, React/Phaser visualizer, Docker packaging, local verification, and end-to-end tests.
2. [Optional Observability Bridge](./2026-07-27-yume-observability-bridge.md) — authenticated Hermes hook ingestion and richer subagent lifecycle telemetry. The core dashboard does not depend on this plan.
3. [Production Asset Pack](./2026-07-27-yume-production-assets.md) — AI-assisted concepts, Aseprite cleanup and animation, final Tiled office, pack swap, and visual release QA.

Execute the plans in this order. The core plan ends with a complete working visualizer using production-shaped placeholder assets. The bridge can be developed while production art is being prepared because both depend only on the core event and asset contracts.

Core Task 1 initializes `main` with `https://github.com/nakanokazuha/ame-no-uzume.git` as `origin`. After each complete, verified task, commit and push `main` before starting the next task. Do not add CI/CD or GitHub Actions until the complete v1 acceptance gate passes; plan that work separately after v1.
