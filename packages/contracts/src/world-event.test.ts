import { compile } from "json-schema-to-typescript";
import { describe, expect, it } from "vitest";

import schemaSource from "../schemas/world-event.schema.json?raw";
import generatedTypes from "./world-event.ts?raw";

const schema = JSON.parse(schemaSource) as Parameters<typeof compile>[0];

describe("generated WorldEvent TypeScript", () => {
  it("matches the current JSON Schema", async () => {
    await expect(compile(schema, "schemas/world-event.schema.json")).resolves.toBe(generatedTypes);
  });
});
