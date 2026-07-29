export interface GridPoint {
  x: number;
  y: number;
}

interface OpenPoint {
  point: GridPoint;
  cost: number;
  score: number;
}

const neighborDeltas: readonly GridPoint[] = [
  { x: 1, y: -1 }, // NE
  { x: 1, y: 1 }, // SE
  { x: -1, y: 1 }, // SW
  { x: -1, y: -1 }, // NW
];

function pointKey({ x, y }: GridPoint): string {
  return `${x},${y}`;
}

function isWalkable(grid: number[][], point: GridPoint): boolean {
  return grid[point.y]?.[point.x] === 0;
}

function scorePoint(point: GridPoint, goal: GridPoint, cost: number): number {
  return cost + Math.abs(goal.x - point.x) + Math.abs(goal.y - point.y);
}

export function findPath(grid: number[][], start: GridPoint, goal: GridPoint): GridPoint[] {
  if (!isWalkable(grid, start) || !isWalkable(grid, goal)) {
    return [];
  }

  const startKey = pointKey(start);
  const goalKey = pointKey(goal);
  const open: OpenPoint[] = [{ point: start, cost: 0, score: scorePoint(start, goal, 0) }];
  const cameFrom = new Map<string, GridPoint>();
  const bestCost = new Map<string, number>([[startKey, 0]]);

  while (open.length > 0) {
    open.sort((left, right) =>
      left.score - right.score || pointKey(left.point).localeCompare(pointKey(right.point)),
    );
    const current = open.shift();
    if (!current) {
      return [];
    }

    if (pointKey(current.point) === goalKey) {
      const path: GridPoint[] = [current.point];
      let previous = cameFrom.get(pointKey(current.point));
      while (previous) {
        path.unshift(previous);
        previous = cameFrom.get(pointKey(previous));
      }
      return path;
    }

    for (const delta of neighborDeltas) {
      const next = { x: current.point.x + delta.x, y: current.point.y + delta.y };
      if (!isWalkable(grid, next)) {
        continue;
      }

      const cost = current.cost + 1;
      if (cost >= (bestCost.get(pointKey(next)) ?? Number.POSITIVE_INFINITY)) {
        continue;
      }

      bestCost.set(pointKey(next), cost);
      cameFrom.set(pointKey(next), current.point);
      open.push({ point: next, cost, score: scorePoint(next, goal, cost) });
    }
  }

  return [];
}
