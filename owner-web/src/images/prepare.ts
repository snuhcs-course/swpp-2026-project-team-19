/**
 * Photos are shrunk in the browser before upload so they meet the server's rules, as the app does
 * (android/.../data/ImageUploadPreparer.kt, and the cover photo rule of LiveOwnerScreenRepository.kt).
 * Re-encoding as JPEG also drops the photo's metadata, such as its location.
 */
export interface ImageRule {
  /** The longest side, in pixels. */
  maxEdge: number;
  maxBytes: number;
}

const MB = 1024 * 1024;

export const IMAGE_RULES = {
  /** Business certificate OCR (spec 3.11.12): JPEG or PNG up to 10 MB. Text needs resolution. */
  certificate: { maxEdge: 2400, maxBytes: 10 * MB },
  /** Application menu photos (spec 3.11.15, 4.1): up to 10 MB each, 60 MB together, 15 photos. */
  menu: { maxEdge: 2400, maxBytes: 10 * MB },
  /** A new bar's cover photo (spec 3.11.17, 3.16.2): up to 2 MB and 2048 px on the longest side. */
  cover: { maxEdge: 2048, maxBytes: 2 * MB },
} satisfies Record<string, ImageRule>;

export const MAX_MENU_PHOTOS = 15;
export const MAX_MENU_PHOTOS_BYTES = 60 * MB;

export interface PreparedImage {
  blob: Blob;
  fileName: string;
  width: number;
  height: number;
}

export class ImagePrepareError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ImagePrepareError";
  }
}

const UNREADABLE = "사진을 읽을 수 없어요. 다른 사진을 골라 주세요.";
const TOO_LARGE = "사진이 너무 커요. 다른 사진을 골라 주세요.";

/** The size to draw at: the longest side at most `maxEdge`, never enlarged. */
export function targetSize(width: number, height: number, maxEdge: number): { width: number; height: number } {
  const scale = Math.min(1, maxEdge / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

const QUALITIES = [0.9, 0.8, 0.7, 0.6];
const SCALES = [1, 0.8, 0.6, 0.45];

/**
 * Encodes at falling quality (90 to 60, as the app does), then at smaller sizes, until the result fits
 * `maxBytes`. `encode(scale, quality)` draws the image at that fraction of its target size.
 */
export async function encodeWithinLimit(
  encode: (scale: number, quality: number) => Promise<Blob>,
  maxBytes: number,
): Promise<{ blob: Blob; scale: number }> {
  for (const scale of SCALES) {
    for (const quality of QUALITIES) {
      const blob = await encode(scale, quality);
      if (blob.size <= maxBytes) return { blob, scale };
    }
  }
  throw new ImagePrepareError(TOO_LARGE);
}

function decode(file: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new ImagePrepareError(UNREADABLE));
    };
    // Browsers apply the photo's EXIF orientation when an <img> is drawn, so the result is upright.
    image.src = url;
  });
}

/** A JPEG of `file` that meets `rule`. Throws ImagePrepareError with a message for the owner. */
export async function prepareImage(file: File, rule: ImageRule): Promise<PreparedImage> {
  if (!file.type.startsWith("image/")) throw new ImagePrepareError(UNREADABLE);
  const image = await decode(file);
  if (!image.naturalWidth || !image.naturalHeight) throw new ImagePrepareError(UNREADABLE);
  const target = targetSize(image.naturalWidth, image.naturalHeight, rule.maxEdge);
  let drawn = target;

  const encode = (scale: number, quality: number) =>
    new Promise<Blob>((resolve, reject) => {
      drawn = { width: Math.max(1, Math.round(target.width * scale)), height: Math.max(1, Math.round(target.height * scale)) };
      const canvas = document.createElement("canvas");
      canvas.width = drawn.width;
      canvas.height = drawn.height;
      const context = canvas.getContext("2d");
      if (!context) return reject(new ImagePrepareError(UNREADABLE));
      context.drawImage(image, 0, 0, drawn.width, drawn.height);
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new ImagePrepareError(UNREADABLE))), "image/jpeg", quality);
    });

  const { blob } = await encodeWithinLimit(encode, rule.maxBytes);
  const base = file.name.replace(/\.[^.]*$/, "") || "photo";
  return { blob, fileName: `${base}.jpg`, width: drawn.width, height: drawn.height };
}
