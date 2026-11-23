import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "../api/errors";
import { BarQuery } from "../bar/BarHomePage";
import { useBarFailure } from "../bar/failures";
import { OwnerScreen } from "../owner/OwnerScreen";
import { useBar, type BarDetail, type OwnedBar } from "../owner/queries";
import { Button, ButtonLink } from "../ui/Button";
import { importPath } from "./ImportEntry";
import { useImportActions } from "./importApi";
import { addPhotos, MAX_IMPORT_PHOTOS, movePhoto, PHOTO_COPY, PhotoPickError, validateMenuPhotoSizes, type ImportPhoto } from "./photoRules";
import { UploadKeys } from "./uploadKey";
import styles from "./menuImport.module.css";

/** The app's steps above the photo screens (OwnerMenuPhotoStage7Screen.kt `MenuPhotoSteps`). */
export function ImportSteps({ step }: { step: 0 | 1 | 2 | 3 }) {
  return (
    <ol className={styles.steps} aria-label="진행 단계">
      {["사진 올리기", "읽기", "확인", "더하기"].map((label, index) => (
        <li key={label} aria-current={index === step ? "step" : undefined}>
          {label}
        </li>
      ))}
    </ol>
  );
}

/**
 * /owner/bars/:barId/menu/import: menu photos to add to the menu (spec 4), as OwnerMenuPhotoSelectionScreen.kt.
 * The owner picks up to 15 photos in the menu's page order, removes or moves them, and uploads them together as a
 * partial update. While an import is unfinished, it opens that import instead.
 */
export function ImportStartPage({ bar }: { bar: OwnedBar }) {
  const detail = useBar(bar.barId);
  return (
    <OwnerScreen title="메뉴판 사진 선택" backTo={`/bars/${bar.barId}/menu`}>
      <BarQuery query={detail}>
        {(data) =>
          data.activeMenuImport ? (
            <div className={styles.screen}>
              <ImportSteps step={0} />
              <p className={styles.notice} role="status">
                진행 중인 메뉴판 작업이 있어요. 먼저 기존 작업을 확인해 주세요.
              </p>
              <ButtonLink to={importPath(data.barId, data.activeMenuImport.menuImportId)}>기존 작업 확인</ButtonLink>
            </div>
          ) : (
            <PhotoPicker bar={data} />
          )
        }
      </BarQuery>
    </OwnerScreen>
  );
}

/** What an upload failure means for the owner (spec 4.4). */
function uploadFailureMessage(failure: unknown): string | null {
  if (!(failure instanceof ApiError)) return null;
  switch (failure.code) {
    case "NETWORK_ERROR":
      return "인터넷 연결을 확인해 주세요. 다시 올리면 같은 요청으로 보내요.";
    case "UPLOAD_TOO_LARGE":
      return "사진이 너무 많거나 커요. 사진 수를 줄이거나 더 작은 사진으로 바꿔 주세요.";
    case "UNSUPPORTED_IMAGE_TYPE": {
      const order = failure.details?.imageOrder;
      return typeof order === "number" ? `${order}번째 사진은 올릴 수 없는 형식이에요. JPEG나 PNG 사진으로 바꿔 주세요.` : PHOTO_COPY.type;
    }
    case "IDEMPOTENCY_KEY_REUSED":
      return "요청이 겹쳤어요. 다시 올려 주세요.";
    default:
      return null;
  }
}

function PhotoPicker({ bar }: { bar: BarDetail }) {
  const navigate = useNavigate();
  const actions = useImportActions(bar.barId);
  const fail = useBarFailure();
  const keys = useRef(new UploadKeys());
  const [photos, setPhotos] = useState<ImportPhoto[]>([]);
  const [busy, setBusy] = useState<"adding" | "uploading" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const urls = useRef(photos);
  urls.current = photos;
  // Thumbnails are object URLs; they are released when the screen is left.
  useEffect(() => () => urls.current.forEach((photo) => URL.revokeObjectURL(photo.previewUrl)), []);

  async function pick(files: File[]) {
    if (files.length === 0 || busy) return;
    setBusy("adding");
    try {
      setPhotos(await addPhotos(photos, files));
      setError(null);
    } catch (failure) {
      setError(failure instanceof PhotoPickError ? failure.message : PHOTO_COPY.unreadable);
    } finally {
      setBusy(null);
    }
  }

  function remove(index: number) {
    const removed = photos[index];
    if (removed) URL.revokeObjectURL(removed.previewUrl);
    setPhotos(photos.filter((_, i) => i !== index));
    setError(null);
  }

  async function upload() {
    if (busy || validateMenuPhotoSizes(photos.map((photo) => photo.file.size)) !== null) return;
    setBusy("uploading");
    setError(null);
    try {
      const accepted = await actions.upload(photos, keys.current.keyFor(bar.barId, photos.map((photo) => photo.id)));
      keys.current.forget();
      void navigate(importPath(bar.barId, accepted.menuImportId), { replace: true });
    } catch (failure) {
      setBusy(null);
      if (failure instanceof ApiError && failure.code === "ACTIVE_IMPORT_EXISTS") {
        // Another device started an import meanwhile: continue that one (4.4), nothing is uploaded again.
        keys.current.forget();
        const existing = failure.details?.menuImportId;
        await actions.refreshBar();
        if (typeof existing === "string") void navigate(importPath(bar.barId, existing), { replace: true, state: { notice: "진행 중인 메뉴판 작업이 있어 그 작업으로 이동했어요." } });
        return;
      }
      if (failure instanceof ApiError && failure.code === "IDEMPOTENCY_KEY_REUSED") keys.current.forget();
      setError(uploadFailureMessage(failure) ?? fail(failure));
    }
  }

  const full = photos.length >= MAX_IMPORT_PHOTOS;
  const valid = validateMenuPhotoSizes(photos.map((photo) => photo.file.size)) === null;
  const locked = busy !== null;

  return (
    <div className={styles.screen}>
      <ImportSteps step={0} />
      <div>
        <h2 className={styles.title}>메뉴판 사진 선택</h2>
        <p className={styles.text}>사진을 최대 15장까지 올릴 수 있어요.</p>
      </div>
      <ul className={styles.photos} aria-label="고른 사진">
        {photos.map((photo, index) => (
          <li key={photo.id} className={styles.photo} aria-label={`메뉴판 사진 ${index + 1}`}>
            <img src={photo.previewUrl} alt="" />
            <span className={styles.order}>{index + 1}</span>
            <span className={styles.photoTools}>
              <button type="button" aria-label={`사진 ${index + 1} 앞으로`} disabled={locked || index === 0} onClick={() => setPhotos(movePhoto(photos, index, -1))}>
                ‹
              </button>
              <button type="button" aria-label={`사진 ${index + 1} 뒤로`} disabled={locked || index === photos.length - 1} onClick={() => setPhotos(movePhoto(photos, index, 1))}>
                ›
              </button>
              <button type="button" aria-label={`사진 ${index + 1} 빼기`} disabled={locked} onClick={() => remove(index)}>
                ×
              </button>
            </span>
          </li>
        ))}
        <li>
          <label className={[styles.addPhoto, full || locked ? styles.addPhotoOff : ""].join(" ")} style={{ position: "relative" }}>
            <span aria-hidden="true">+</span>
            사진 추가
            <input
              type="file"
              accept="image/jpeg,image/png"
              multiple
              disabled={locked}
              onClick={(event) => {
                // OwnerMenuPhotoStage7Screen.kt: with 15 photos the picker does not open.
                if (full) {
                  event.preventDefault();
                  setError(PHOTO_COPY.tooMany);
                }
              }}
              onChange={(event) => {
                const files = [...(event.currentTarget.files ?? [])];
                event.currentTarget.value = "";
                void pick(files);
              }}
            />
          </label>
        </li>
      </ul>
      <div className={styles.spread}>
        <p className={styles.text}>메뉴판 순서대로 올려주세요.</p>
        <p className={styles.text}>{photos.length}/15</p>
      </div>
      <ul className={styles.guide}>
        <li>한 장에 한 면씩, 글자와 가격이 잘리지 않게</li>
        <li>빛 반사 없이 정면에서</li>
      </ul>
      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
      <Button busy={busy === "uploading"} disabled={!valid || locked} onClick={() => void upload()}>
        {busy === "adding" ? "사진을 확인하고 있어요" : busy === "uploading" ? "사진을 올리고 있어요" : `사진 ${photos.length}장 올리기`}
      </Button>
    </div>
  );
}
