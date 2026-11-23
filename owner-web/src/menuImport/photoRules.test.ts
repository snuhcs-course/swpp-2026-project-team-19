import { describe, expect, it } from "vitest";
import {
  addPhotos,
  menuPhotoSignature,
  movePhoto,
  PHOTO_COPY,
  PhotoPickError,
  validateMenuPhotoSizes,
  type ImportPhoto,
} from "./photoRules";
import { UploadKeys } from "./uploadKey";

const MB = 1024 * 1024;
const JPEG = [0xff, 0xd8, 0xff, 0xe0];
const PNG = [137, 80, 78, 71, 13, 10, 26, 10];

/** A file of `size` bytes starting with `head`. */
function photo(name: string, head: number[], size = 64, type = head === PNG ? "image/png" : "image/jpeg"): File {
  const bytes = new Uint8Array(size);
  bytes.set(head.slice(0, size));
  return new File([bytes], name, { type });
}

/** A file that claims `size` bytes without allocating them. */
function sized(name: string, size: number): File {
  const file = photo(name, JPEG);
  Object.defineProperty(file, "size", { value: size });
  return file;
}

const url = (file: File) => `blob:${file.name}`;

describe("menu photo limits (OwnerMenuPhotoStore.kt)", () => {
  // OwnerMenuPhotoPolicyTest.kt countAndSizeBoundariesCoverZeroOneFifteenSixteen
  it("allows one to fifteen photos of up to 10 MB each and 60 MB together", () => {
    expect(validateMenuPhotoSizes([])).toBe(PHOTO_COPY.none);
    expect(validateMenuPhotoSizes([1])).toBeNull();
    expect(validateMenuPhotoSizes(Array(15).fill(1))).toBeNull();
    expect(validateMenuPhotoSizes(Array(16).fill(1))).toBe(PHOTO_COPY.tooMany);
    expect(validateMenuPhotoSizes(Array(6).fill(10 * MB))).toBeNull();
    expect(validateMenuPhotoSizes(Array(7).fill(10 * MB))).toBe(PHOTO_COPY.totalTooLarge);
    expect(validateMenuPhotoSizes([10 * MB + 1])).toBe(PHOTO_COPY.tooLarge);
    expect(validateMenuPhotoSizes([0])).toBe(PHOTO_COPY.unreadable);
    expect(validateMenuPhotoSizes([-1])).toBe(PHOTO_COPY.unreadable);
  });

  // OwnerMenuPhotoPolicyTest.kt jpegAndPngMagicAreAcceptedButUnsupportedFormatsRejected
  it("tells JPEG and PNG from their first bytes and refuses other formats", () => {
    expect(menuPhotoSignature(new Uint8Array([0xff, 0xd8, 0xff, 0, 0, 0, 0, 0]))).toBe("image/jpeg");
    expect(menuPhotoSignature(new Uint8Array(PNG))).toBe("image/png");
    expect(menuPhotoSignature(new Uint8Array([0x52, 0x49, 0x46, 0x46]))).toBeNull();
    expect(menuPhotoSignature(new Uint8Array([]))).toBeNull();
  });

  // OwnerPhotoStage7Test.kt photoLimitsRejectZeroAndSixteenAllowFifteen
  it("adds fifteen photos in the order picked and refuses a sixteenth", async () => {
    const fifteen = await addPhotos([], Array.from({ length: 15 }, (_, i) => photo(`p${i + 1}.jpg`, JPEG)), url);
    expect(fifteen.map((p) => p.file.name)).toEqual(Array.from({ length: 15 }, (_, i) => `p${i + 1}.jpg`));
    expect(fifteen.map((p) => p.type)).toEqual(Array(15).fill("image/jpeg"));
    await expect(addPhotos(fifteen, [photo("p16.jpg", JPEG)], url)).rejects.toThrow(PHOTO_COPY.tooMany);
  });

  // OwnerMenuPhotoStore.kt `add`: one bad photo keeps the whole pick out
  it("adds none of a pick when one of its photos cannot be sent", async () => {
    const before = await addPhotos([], [photo("first.jpg", JPEG)], url);
    for (const [files, message] of [
      [[photo("ok.png", PNG), photo("menu.webp", [0x52, 0x49, 0x46, 0x46], 64, "image/webp")], PHOTO_COPY.type],
      [[photo("ok.jpg", JPEG), sized("big.jpg", 10 * MB + 1)], PHOTO_COPY.tooLarge],
      // The type the browser declares must match the content, as the server checks (415).
      [[photo("png-named.jpg", PNG, 64, "image/jpeg")], PHOTO_COPY.type],
    ] as const) {
      const failure = addPhotos(before, [...files], url);
      await expect(failure).rejects.toBeInstanceOf(PhotoPickError);
      await expect(failure).rejects.toThrow(message);
    }
    expect(before.map((p) => p.file.name)).toEqual(["first.jpg"]);
  });

  it("refuses a photo that takes the photos over 60 MB together", async () => {
    const six = await addPhotos([], Array.from({ length: 6 }, (_, i) => sized(`p${i}.jpg`, 10 * MB)), url);
    await expect(addPhotos(six, [sized("one-more.jpg", 1)], url)).rejects.toThrow(PHOTO_COPY.totalTooLarge);
  });

  it("moves a photo one place and leaves the ends alone", () => {
    const photos = ["a", "b", "c"];
    expect(movePhoto(photos, 1, -1)).toEqual(["b", "a", "c"]);
    expect(movePhoto(photos, 1, 1)).toEqual(["a", "c", "b"]);
    expect(movePhoto(photos, 0, -1)).toEqual(photos);
    expect(movePhoto(photos, 2, 1)).toEqual(photos);
  });
});

describe("the upload key (LiveOwnerScreenRepository.kt submitPhotoImportLive)", () => {
  function keys() {
    let next = 0;
    return new UploadKeys(() => `key-${++next}`);
  }
  const ids = (photos: Pick<ImportPhoto, "id">[]) => photos.map((p) => p.id);

  // MenuUploadRetryCacheTest.kt networkRetryReusesExactPreparedBytesAndKey
  it("sends the same photos again with the same key after a lost answer", () => {
    const upload = keys();
    const first = upload.keyFor("bar-1", ids([{ id: "a" }, { id: "b" }]));
    expect(upload.keyFor("bar-1", ["a", "b"])).toBe(first);
  });

  it("makes a new key for other photos, another order or another bar", () => {
    const upload = keys();
    const first = upload.keyFor("bar-1", ["a", "b"]);
    expect(upload.keyFor("bar-1", ["b", "a"])).not.toBe(first);
    expect(upload.keyFor("bar-1", ["a"])).not.toBe(first);
    expect(upload.keyFor("bar-2", ["a"])).not.toBe(upload.keyFor("bar-1", ["a"]));
  });

  // MenuUploadRetryCacheTest.kt keyConflictChangesOnlyKeyAndExplicitNewAttemptDropsCachedPayload
  it("starts a new upload with a new key once the last one was accepted or its key refused", () => {
    const upload = keys();
    expect(upload.keyFor("bar-1", ["a"])).toBe("key-1");
    upload.forget();
    expect(upload.keyFor("bar-1", ["a"])).toBe("key-2");
  });
});
