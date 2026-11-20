import { describe, expect, it, vi } from "vitest";
import { encodeWithinLimit, IMAGE_RULES, ImagePrepareError, targetSize } from "./prepare";

describe("targetSize", () => {
  it("shrinks the longest side to the limit and keeps the shape", () => {
    expect(targetSize(4032, 3024, IMAGE_RULES.cover.maxEdge)).toEqual({ width: 2048, height: 1536 });
    expect(targetSize(3000, 6000, IMAGE_RULES.menu.maxEdge)).toEqual({ width: 1200, height: 2400 });
  });

  it("never enlarges a small photo", () => {
    expect(targetSize(800, 600, 2048)).toEqual({ width: 800, height: 600 });
  });
});

describe("encodeWithinLimit", () => {
  const blobOf = (bytes: number) => new Blob([new Uint8Array(bytes)]);

  it("lowers the quality first, as the app does", async () => {
    const encode = vi.fn(async (_scale: number, quality: number) => blobOf(quality > 0.7 ? 3000 : 1000));

    const { blob, scale } = await encodeWithinLimit(encode, 2000);

    expect(blob.size).toBe(1000);
    expect(scale).toBe(1);
    expect(encode.mock.calls.map(([s, q]) => [s, q])).toEqual([
      [1, 0.9],
      [1, 0.8],
      [1, 0.7],
    ]);
  });

  it("then draws smaller", async () => {
    const encode = vi.fn(async (scale: number) => blobOf(scale < 1 ? 500 : 5000));

    const { scale } = await encodeWithinLimit(encode, 1000);

    expect(scale).toBe(0.8);
  });

  it("gives up with a message when nothing fits", async () => {
    await expect(encodeWithinLimit(async () => blobOf(5000), 1000)).rejects.toBeInstanceOf(ImagePrepareError);
  });
});
