/**
 * The menu photos an owner picks before a menu import (spec 4.1), ported from
 * android/.../ui/owner/OwnerMenuPhotoStore.kt (`validateMenuPhotoSizes`, `menuPhotoSignature`, `add`).
 *
 * As in the app, photos are sent as they are: JPEG or PNG, told apart by their first bytes (the server compares
 * the content with the declared type, 4.1), never shrunk. A photo over 10 MB, or one that would take the photos
 * over 60 MB together, is refused when it is picked.
 */
export const MAX_IMPORT_PHOTOS = 15;
export const MAX_IMPORT_PHOTO_BYTES = 10 * 1024 * 1024;
export const MAX_IMPORT_TOTAL_BYTES = 60 * 1024 * 1024;

export const PHOTO_COPY = {
  none: "메뉴판 사진을 한 장 이상 선택해 주세요.",
  tooMany: "사진은 최대 15장까지 선택할 수 있어요.",
  unreadable: "읽을 수 없는 사진이 있어요. 다시 선택해 주세요.",
  tooLarge: "사진 한 장은 최대 10MB까지 가능해요.",
  totalTooLarge: "전체 사진은 60MB 이하여야 해요.",
  type: "JPEG 또는 PNG 사진만 올릴 수 있어요.",
} as const;

export type PhotoType = "image/jpeg" | "image/png";

/** A picked photo: the file, its type read from its bytes, and a URL for its thumbnail. */
export interface ImportPhoto {
  id: string;
  file: File;
  type: PhotoType;
  previewUrl: string;
}

/** `validateMenuPhotoSizes`: the message for photos of these sizes, or null when they can be sent. */
export function validateMenuPhotoSizes(sizes: readonly number[]): string | null {
  if (sizes.length === 0) return PHOTO_COPY.none;
  if (sizes.length > MAX_IMPORT_PHOTOS) return PHOTO_COPY.tooMany;
  if (sizes.some((size) => size <= 0)) return PHOTO_COPY.unreadable;
  if (sizes.some((size) => size > MAX_IMPORT_PHOTO_BYTES)) return PHOTO_COPY.tooLarge;
  if (sizes.reduce((sum, size) => sum + size, 0) > MAX_IMPORT_TOTAL_BYTES) return PHOTO_COPY.totalTooLarge;
  return null;
}

const PNG = [137, 80, 78, 71, 13, 10, 26, 10];

/** `menuPhotoSignature`: JPEG or PNG from the first bytes, or null for anything else. */
export function menuPhotoSignature(bytes: Uint8Array): PhotoType | null {
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image/jpeg";
  if (bytes.length >= 8 && PNG.every((value, index) => bytes[index] === value)) return "image/png";
  return null;
}

export class PhotoPickError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PhotoPickError";
  }
}

async function firstBytes(file: File): Promise<Uint8Array> {
  try {
    return new Uint8Array(await file.slice(0, 8).arrayBuffer());
  } catch {
    throw new PhotoPickError(PHOTO_COPY.unreadable);
  }
}

let sequence = 0;

/**
 * `OwnerMenuPhotoStore.add`: the photos after adding `files`, in the order picked. All or nothing: when one
 * photo cannot be sent, none of this pick is added and the photos picked before stay as they were.
 */
export async function addPhotos(
  existing: readonly ImportPhoto[],
  files: readonly File[],
  objectUrl: (file: File) => string = (file) => URL.createObjectURL(file),
): Promise<ImportPhoto[]> {
  if (existing.length + files.length > MAX_IMPORT_PHOTOS) throw new PhotoPickError(PHOTO_COPY.tooMany);
  let total = existing.reduce((sum, photo) => sum + photo.file.size, 0);
  const added: Omit<ImportPhoto, "previewUrl">[] = [];
  for (const file of files) {
    if (file.size <= 0) throw new PhotoPickError("빈 사진은 등록할 수 없어요.");
    if (file.size > MAX_IMPORT_PHOTO_BYTES) throw new PhotoPickError(PHOTO_COPY.tooLarge);
    if (total + file.size > MAX_IMPORT_TOTAL_BYTES) throw new PhotoPickError(PHOTO_COPY.totalTooLarge);
    const type = menuPhotoSignature(await firstBytes(file));
    // A declared type other than the content's is refused by the server (415), as the app refuses it here.
    const declared = file.type || null;
    if (type === null || (declared !== null && declared !== type)) throw new PhotoPickError(PHOTO_COPY.type);
    total += file.size;
    sequence += 1;
    added.push({ id: `menu-photo-${sequence}`, file, type });
  }
  const problem = validateMenuPhotoSizes([...existing, ...added].map((photo) => photo.file.size));
  if (problem) throw new PhotoPickError(problem);
  return [...existing, ...added.map((photo) => ({ ...photo, previewUrl: objectUrl(photo.file) }))];
}

/** Moves a photo one place earlier or later; the order sent is the menu's page order (4.1 `imageOrder`). */
export function movePhoto<T>(photos: readonly T[], index: number, offset: number): T[] {
  const target = index + offset;
  if (index < 0 || index >= photos.length || target < 0 || target >= photos.length) return [...photos];
  const next = [...photos];
  next.splice(target, 0, ...next.splice(index, 1));
  return next;
}
