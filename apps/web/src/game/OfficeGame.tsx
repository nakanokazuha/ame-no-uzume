import { useEffect, useRef, type JSX } from "react";
import Phaser from "phaser";
import type { BootstrapResponse } from "../api/client";
import type { WorldState } from "../store/world";
import { OfficeScene } from "./OfficeScene";

interface WorldStore {
  getState: () => WorldState;
  subscribe: (listener: (state: WorldState, previousState: WorldState) => void) => () => void;
}

export interface OfficeGameProps {
  bootstrap: BootstrapResponse;
  store: WorldStore;
}

export function OfficeGame({ bootstrap, store }: OfficeGameProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return undefined;
    }

    const scene = new OfficeScene({ bootstrap, store });
    const game = new Phaser.Game({
      type: Phaser.AUTO,
      parent: container,
      backgroundColor: "#172126",
      pixelArt: true,
      roundPixels: true,
      antialias: false,
      scale: {
        mode: Phaser.Scale.RESIZE,
        autoCenter: Phaser.Scale.CENTER_BOTH,
      },
      scene: [scene],
    });

    return () => game.destroy(true);
  }, [bootstrap, store]);

  return <div className="office" data-testid="office-canvas" ref={containerRef} />;
}
