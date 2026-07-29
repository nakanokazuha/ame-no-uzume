export interface WorldPoint {
  x: number;
  y: number;
}

export function tileToWorld(
  tileX: number,
  tileY: number,
  tileWidth: number,
  tileHeight: number,
): WorldPoint {
  return {
    x: Math.round(((tileX - tileY) * tileWidth) / 2),
    y: Math.round(((tileX + tileY) * tileHeight) / 2),
  };
}
