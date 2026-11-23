/**
 * The Idempotency-Key of a menu photo upload (spec 4.1, 4.3), as LiveOwnerScreenRepository.kt
 * `submitPhotoImportLive` keeps it: a new key for every new upload, and the same key only when the same photos
 * of the same bar are sent again because no answer came back. The key is forgotten once the server accepted
 * the upload, and when the server says it was used for other photos (409 IDEMPOTENCY_KEY_REUSED).
 */
export class UploadKeys {
  private pending: { barId: string; photos: string; key: string } | null = null;

  constructor(private readonly newKey: () => string = () => crypto.randomUUID()) {}

  /** The key for sending these photos, in this order, to this bar. */
  keyFor(barId: string, photoIds: readonly string[]): string {
    const photos = photoIds.join("\n");
    if (this.pending && this.pending.barId === barId && this.pending.photos === photos) return this.pending.key;
    this.pending = { barId, photos, key: this.newKey() };
    return this.pending.key;
  }

  /** The upload was accepted (202), or its key must not be used again. */
  forget(): void {
    this.pending = null;
  }
}
