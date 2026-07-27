import { mkdirSync, writeFileSync } from "node:fs";
import { PNG } from "pngjs";

function image(width, height, paint) {
  const png = new PNG({ width, height });
  paint(png);
  return PNG.sync.write(png);
}

function setPixel(png, x, y, [r, g, b, a = 255]) {
  const offset = (png.width * y + x) << 2;
  [png.data[offset], png.data[offset + 1], png.data[offset + 2], png.data[offset + 3]] =
    [r, g, b, a];
}

mkdirSync("asset-packs/placeholder/tiles", { recursive: true });
mkdirSync("asset-packs/placeholder/atlases", { recursive: true });

writeFileSync(
  "asset-packs/placeholder/tiles/office.png",
  image(64, 32, (png) => {
    for (let y = 0; y < 32; y += 1) {
      const half = y < 16 ? y * 2 : (31 - y) * 2;
      for (let x = 31 - half; x <= 32 + half; x += 1) {
        setPixel(png, x, y, [92, 118, 126, 255]);
      }
    }
  }),
);

writeFileSync(
  "asset-packs/placeholder/atlases/characters.png",
  image(32 * 31, 48, (png) => {
    for (let frame = 0; frame < 31; frame += 1) {
      for (let y = 12; y < 44; y += 1) {
        for (let x = frame * 32 + 10; x < frame * 32 + 22; x += 1) {
          setPixel(
            png,
            x,
            y,
            frame < 2 ? [238, 196, 84, 255] : [94, 166, 206, 255],
          );
        }
      }
    }
  }),
);

const frames = Object.fromEntries(
  Array.from({ length: 31 }, (_, frame) => [
    `frame-${frame}`,
    {
      frame: { x: frame * 32, y: 0, w: 32, h: 48 },
      rotated: false,
      trimmed: false,
      spriteSourceSize: { x: 0, y: 0, w: 32, h: 48 },
      sourceSize: { w: 32, h: 48 },
    },
  ]),
);
writeFileSync(
  "asset-packs/placeholder/atlases/characters.json",
  `${JSON.stringify({ frames, meta: { image: "characters.png", scale: "1" } }, null, 2)}\n`,
);

mkdirSync("asset-packs/placeholder/maps", { recursive: true });
const width = 12;
const height = 12;
const layer = (id, name, data) => ({
  id,
  name,
  type: "tilelayer",
  width,
  height,
  x: 0,
  y: 0,
  data,
});
writeFileSync(
  "asset-packs/placeholder/maps/office.json",
  `${JSON.stringify(
    {
      compressionlevel: -1,
      height,
      infinite: false,
      layers: [
        layer(1, "floor", Array(width * height).fill(1)),
        layer(2, "walls", Array(width * height).fill(0)),
        layer(3, "furniture-low", Array(width * height).fill(0)),
        layer(4, "furniture-high", Array(width * height).fill(0)),
      ],
      nextlayerid: 5,
      nextobjectid: 1,
      orientation: "isometric",
      renderorder: "right-down",
      tileheight: 32,
      tilesets: [
        {
          firstgid: 1,
          columns: 1,
          image: "../tiles/office.png",
          imageheight: 32,
          imagewidth: 64,
          name: "office",
          tilecount: 1,
          tileheight: 32,
          tilewidth: 64,
        },
      ],
      tilewidth: 64,
      type: "map",
      version: "1.10",
      width,
    },
    null,
    2,
  )}\n`,
);
