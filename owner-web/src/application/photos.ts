import type { PreparedImage } from "../images/prepare";
import type { PickedPhoto } from "./ApplicationProvider";

let sequence = 0;

/** A photo picked on this visit, with an object URL for its thumbnail (revoked when it is removed). */
export function pickedPhoto(image: PreparedImage): PickedPhoto {
  sequence += 1;
  return { id: `photo-${sequence}`, image, previewUrl: URL.createObjectURL(image.blob) };
}
