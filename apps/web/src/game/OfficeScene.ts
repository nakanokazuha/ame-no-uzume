import Phaser from "phaser";
import type { AgentView } from "@yume/contracts";
import type { BootstrapResponse } from "../api/client";
import type { WorldState } from "../store/world";
import { tileToWorld, type WorldPoint } from "./coordinates";
import {
  animationKey,
  movementTargetPositions,
  needsStatusMarker,
  snapToPixel,
  statusMarkerPosition,
} from "./sprites";

type WorldStore = {
  getState: () => WorldState;
  subscribe: (listener: (state: WorldState, previousState: WorldState) => void) => () => void;
};

type Anchor = { x: number; y: number };

interface DragOrigin {
  pointerX: number;
  pointerY: number;
  scrollX: number;
  scrollY: number;
}

const zoomLevels = [1, 1.5, 2] as const;

export interface OfficeSceneOptions {
  bootstrap: BootstrapResponse;
  store: WorldStore;
}

export class OfficeScene extends Phaser.Scene {
  private readonly bootstrap: BootstrapResponse;
  private readonly store: WorldStore;
  private readonly agentSprites = new Map<string, Phaser.GameObjects.Sprite>();
  private readonly statusMarkers = new Map<string, Phaser.GameObjects.Arc>();
  private dragOrigin: DragOrigin | undefined;
  private map: Phaser.Tilemaps.Tilemap | undefined;
  private unsubscribe: (() => void) | undefined;

  public constructor({ bootstrap, store }: OfficeSceneOptions) {
    super("office");
    this.bootstrap = bootstrap;
    this.store = store;
  }

  public preload(): void {
    const pack = this.bootstrap.asset_pack.id;
    this.load.tilemapTiledJSON("office", `/asset-packs/${pack}/${this.bootstrap.asset_pack.map}`);
    this.load.image("office-tiles", `/asset-packs/${pack}/tiles/office.png`);
    this.load.atlas(
      "characters",
      `/asset-packs/${pack}/atlases/characters.png`,
      `/asset-packs/${pack}/${this.bootstrap.asset_pack.atlas}`,
    );
  }

  public create(): void {
    const map = this.make.tilemap({ key: "office" });
    const tiles = map.addTilesetImage("office", "office-tiles");
    if (!tiles) {
      throw new Error("Office tileset could not be loaded.");
    }

    for (const name of ["floor", "walls", "furniture-low", "furniture-high"]) {
      const layer = map.createLayer(name, tiles);
      if (layer && name === "furniture-high") {
        layer.setDepth(10_000);
      }
    }

    this.map = map;
    this.createAnimations();
    this.configureCamera();
    this.configureInput();
    this.syncAgents(this.store.getState().agents);
    this.unsubscribe = this.store.subscribe((state, previousState) => {
      if (state.agents !== previousState.agents) {
        this.syncAgents(state.agents);
      }
    });
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, this.shutdown, this);
  }

  public syncAgents(agents: AgentView[]): void {
    const activeIds = new Set(agents.map((agent) => agent.agent_id));
    for (const agent of agents) {
      this.upsertAgent(agent);
    }

    for (const [agentId, sprite] of this.agentSprites) {
      if (!activeIds.has(agentId)) {
        this.walkTo(sprite, agentId, this.anchorFor("lobby"), () => {
          sprite.destroy();
          this.statusMarkers.get(agentId)?.destroy();
          this.statusMarkers.delete(agentId);
        });
        this.agentSprites.delete(agentId);
      }
    }
  }

  public fitOffice(): void {
    const map = this.map;
    if (!map) {
      return;
    }

    const desired = Math.min(this.scale.width / map.widthInPixels, this.scale.height / map.heightInPixels);
    const zoom = zoomLevels.reduce((closest, level) =>
      Math.abs(level - desired) < Math.abs(closest - desired) ? level : closest,
    );
    this.cameras.main.setZoom(zoom);
    this.cameras.main.centerOn(map.widthInPixels / 2, map.heightInPixels / 2);
  }

  private createAnimations(): void {
    for (const [key, frames] of Object.entries(this.bootstrap.asset_pack.animations)) {
      if (this.anims.exists(key)) {
        continue;
      }
      this.anims.create({
        key,
        frames: frames.map((frame) => ({ key: "characters", frame: `frame-${frame}` })),
        frameRate: 6,
        repeat: -1,
      });
    }
  }

  private configureCamera(): void {
    const map = this.map;
    if (!map) {
      return;
    }
    this.cameras.main.setBounds(0, 0, map.widthInPixels, map.heightInPixels);
    this.fitOffice();
  }

  private configureInput(): void {
    this.input.on("pointerdown", (pointer: Phaser.Input.Pointer, targets: Phaser.GameObjects.GameObject[]) => {
      if (targets.length > 0) {
        return;
      }
      this.dragOrigin = {
        pointerX: pointer.x,
        pointerY: pointer.y,
        scrollX: this.cameras.main.scrollX,
        scrollY: this.cameras.main.scrollY,
      };
    });
    this.input.on("pointermove", (pointer: Phaser.Input.Pointer) => {
      const origin = this.dragOrigin;
      if (!origin || !pointer.isDown) {
        return;
      }
      this.cameras.main.setScroll(
        Math.round(origin.scrollX - (pointer.x - origin.pointerX)),
        Math.round(origin.scrollY - (pointer.y - origin.pointerY)),
      );
    });
    this.input.on("pointerup", (_pointer: Phaser.Input.Pointer, targets: Phaser.GameObjects.GameObject[]) => {
      this.dragOrigin = undefined;
      if (targets.length === 0) {
        this.store.getState().selectAgent(null);
      }
    });
    this.input.on(
      "wheel",
      (
        _pointer: Phaser.Input.Pointer,
        _objects: Phaser.GameObjects.GameObject[],
        _deltaX: number,
        deltaY: number,
      ) => {
        const current = this.closestZoomIndex(this.cameras.main.zoom);
        const next = Phaser.Math.Clamp(current + Math.sign(deltaY), 0, zoomLevels.length - 1);
        const zoom = zoomLevels[next];
        if (zoom !== undefined) {
          this.cameras.main.setZoom(zoom);
        }
      },
    );
  }

  private closestZoomIndex(zoom: number): number {
    const [firstZoom] = zoomLevels;
    let closestIndex = 0;
    let closestDistance = Math.abs(firstZoom - zoom);
    for (let index = 1; index < zoomLevels.length; index += 1) {
      const level = zoomLevels[index];
      if (level !== undefined) {
        const distance = Math.abs(level - zoom);
        if (distance < closestDistance) {
          closestIndex = index;
          closestDistance = distance;
        }
      }
    }
    return closestIndex;
  }

  private upsertAgent(agent: AgentView): void {
    const target = this.anchorFor(agent.room);
    const key = animationKey(agent, this.bootstrap.asset_pack.animations);
    let sprite = this.agentSprites.get(agent.agent_id);
    if (!sprite) {
      const position = this.worldPosition(target);
      sprite = this.add.sprite(position.x, position.y, "characters", "frame-0");
      sprite.setOrigin(0.5, 1).setDepth(position.y).setInteractive({ useHandCursor: true });
      sprite.on("pointerup", () => this.store.getState().selectAgent(agent.agent_id));
      this.agentSprites.set(agent.agent_id, sprite);
    }

    this.syncStatusMarker(agent, sprite);
    sprite.play(key, true);
    this.walkTo(sprite, agent.agent_id, target);
  }

  private syncStatusMarker(agent: AgentView, sprite: Phaser.GameObjects.Sprite): void {
    const existing = this.statusMarkers.get(agent.agent_id);
    if (!needsStatusMarker(agent)) {
      existing?.destroy();
      this.statusMarkers.delete(agent.agent_id);
      return;
    }

    const position = statusMarkerPosition(sprite);
    const marker = existing ?? this.add.circle(position.x, position.y, 4, 0xffd166);
    marker.setDepth(sprite.depth + 1);
    marker.setPosition(Math.round(position.x), Math.round(position.y));
    this.statusMarkers.set(agent.agent_id, marker);
  }

  private walkTo(
    sprite: Phaser.GameObjects.Sprite,
    agentId: string,
    anchor: Anchor,
    onComplete?: () => void,
  ): void {
    const target = this.worldPosition(anchor);
    const movementTargets = movementTargetPositions(target);
    const marker = this.statusMarkers.get(agentId);
    const targets: Phaser.GameObjects.GameObject[] = marker ? [sprite, marker] : [sprite];
    this.tweens.killTweensOf(targets);
    this.tweens.add({
      targets: sprite,
      x: movementTargets.sprite.x,
      y: movementTargets.sprite.y,
      duration: 240,
      ease: "Linear",
      onComplete: () => {
        sprite.setDepth(target.y);
        marker?.setDepth(target.y + 1);
        onComplete?.();
      },
    });
    if (marker) {
      this.tweens.add({
        targets: marker,
        x: movementTargets.marker.x,
        y: movementTargets.marker.y,
        duration: 240,
        ease: "Linear",
      });
    }
  }

  private anchorFor(room: AgentView["room"]): Anchor {
    const anchors = this.bootstrap.asset_pack.anchors;
    const anchor = anchors[room] ?? anchors["work"];
    if (!anchor) {
      throw new Error("Validated asset pack is missing a work anchor.");
    }
    return anchor;
  }

  private worldPosition(anchor: Anchor): WorldPoint {
    const map = this.map;
    if (!map) {
      return { x: 0, y: 0 };
    }
    const projected = tileToWorld(anchor.x, anchor.y, map.tileWidth, map.tileHeight);
    return snapToPixel({ x: map.widthInPixels / 2 + projected.x, y: projected.y + map.tileHeight });
  }

  private shutdown(): void {
    this.unsubscribe?.();
    this.unsubscribe = undefined;
    this.dragOrigin = undefined;
  }
}
