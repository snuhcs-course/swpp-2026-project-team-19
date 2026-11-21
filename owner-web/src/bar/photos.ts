/**
 * The bar photo order (spec 3.16), ported from android/.../ui/owner/OwnerBarEditRules.kt and the photo
 * screen OwnerPhotoHtmlV4Screen.kt. The first photo is the cover; the arrows move only the others, and
 * "대표 사진 등록" is the only way to move a photo to the front.
 */
export const MAX_BAR_PHOTOS = 15;

/** `moveBarPhoto`: moves one place, or returns the list unchanged when it cannot. */
export function movePhoto<T>(photos: readonly T[], index: number, offset: number): T[] {
  const target = index + offset;
  if (index < 0 || index >= photos.length || target < 0 || target >= photos.length) return [...photos];
  const next = [...photos];
  next.splice(target, 0, ...next.splice(index, 1));
  return next;
}

/** `makeCoverPhoto`: moves a photo to the front. */
export function makeCover<T>(photos: readonly T[], index: number): T[] {
  if (index < 0 || index >= photos.length) return [...photos];
  const next = [...photos];
  next.unshift(...next.splice(index, 1));
  return next;
}

/** `moveSecondaryBarPhoto`: the arrows never move the cover, nor a photo into its place. */
export function moveSecondaryPhoto<T>(photos: readonly T[], index: number, offset: number): T[] {
  return index <= 0 || index + offset <= 0 ? [...photos] : movePhoto(photos, index, offset);
}

/** How many of `picked` can still be added: the bar holds at most 15, counting those still uploading. */
export const photoSlots = (current: number, waiting: number): number => Math.max(0, MAX_BAR_PHOTOS - current - waiting);

/**
 * Deleting is refused for the last photo, as in the app (OwnerPhotoHtmlV4Screen.kt "마지막 사진은 삭제할 수
 * 없어요."). The spec would allow it (3.16.1); keeping the app's rule was decided for I5-P6.
 */
export const canDeletePhoto = (count: number): boolean => count > 1;
