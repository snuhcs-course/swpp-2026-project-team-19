import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/errors";
import { IMAGE_RULES, ImagePrepareError, prepareImage } from "../images/prepare";
import { OwnerScreen } from "../owner/OwnerScreen";
import { useBar, useBarPhotoActions, type BarDetail, type BarPhoto, type OwnedBar } from "../owner/queries";
import { BottomSheet } from "../ui/BottomSheet";
import { Button, ButtonLink } from "../ui/Button";
import { BarQuery } from "./BarHomePage";
import { useBarFailure } from "./failures";
import { canDeletePhoto, makeCover, moveSecondaryPhoto, photoSlots } from "./photos";
import { useLeaveGuard } from "./useLeaveGuard";
import styles from "./bar.module.css";

/**
 * /owner/bars/:barId/photos: the bar photos (spec 3.16), as the app's OwnerPhotoHtmlV4Screen.kt. Each change
 * is saved at once: adding uploads one photo at a time (3.16.2), the arrows and "대표 사진 등록" send the new
 * order (3.16.4), deleting asks first (3.16.3). Only one change runs at a time, as in the app.
 */
export function BarPhotosPage({ bar }: { bar: OwnedBar }) {
  const detail = useBar(bar.barId);
  return (
    <OwnerScreen title="매장 사진 편집" backTo={`/bars/${bar.barId}/info`}>
      <BarQuery query={detail} keepDataOnRefetchError>
        {(data) => <PhotoEditor bar={data} />}
      </BarQuery>
    </OwnerScreen>
  );
}

interface Upload {
  key: number;
  file: File;
  previewUrl: string;
  status: "waiting" | "uploading" | "failed";
  error?: string;
}

const LIMIT = "매장 사진은 최대 15장까지 등록할 수 있어요.";
const LIMIT_REACHED = "사진이 이미 15장이에요. 사진을 지운 뒤 다시 추가해 주세요.";

/** What an upload failure means for that photo (spec 3.16.6). */
function uploadMessage(failure: unknown): string | null {
  if (failure instanceof ImagePrepareError) return failure.message;
  if (!(failure instanceof ApiError)) return null;
  switch (failure.code) {
    case "UPLOAD_TOO_LARGE":
      return "사진이 너무 커요. 다른 사진을 골라 주세요.";
    case "UNSUPPORTED_IMAGE_TYPE":
      return "이 사진은 올릴 수 없어요. 다른 사진을 골라 주세요.";
    case "VALIDATION_FAILED":
      return failure.fieldErrors.some((item) => item.code === "IMAGE_DIMENSIONS_TOO_LARGE")
        ? "사진 크기가 너무 커요. 다른 사진을 골라 주세요."
        : null;
    default:
      return null;
  }
}

function PhotoEditor({ bar }: { bar: BarDetail }) {
  const actions = useBarPhotoActions(bar.barId);
  const photos = bar.photos;
  const [queue, setQueue] = useState<Upload[]>([]);
  const [busy, setBusy] = useState(false);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const nextKey = useRef(0);
  const running = useRef(false);
  const uploading = queue.some((item) => item.status === "uploading");
  // Waiting or failed photos are not on the server yet: leaving asks first. While a request runs, leaving
  // is refused, since it cannot be taken back.
  const guard = useLeaveGuard(queue.some((item) => item.status !== "uploading"), busy || uploading);
  const fail = useBarFailure(guard.release);

  const update = useCallback((key: number, change: Partial<Upload> | null) => {
    setQueue((current) => {
      if (change) return current.map((item) => (item.key === key ? { ...item, ...change } : item));
      const gone = current.find((item) => item.key === key);
      if (gone) URL.revokeObjectURL(gone.previewUrl);
      return current.filter((item) => item.key !== key);
    });
  }, []);

  // Uploads one waiting photo at a time (spec 3.16.2: several photos go one by one), never during another change.
  useEffect(() => {
    if (running.current || busy) return;
    const next = queue.find((item) => item.status === "waiting");
    if (!next) return;
    running.current = true;
    update(next.key, { status: "uploading", error: undefined });
    void (async () => {
      try {
        await actions.add(await prepareImage(next.file, IMAGE_RULES.cover));
        update(next.key, null);
      } catch (failure) {
        if (failure instanceof ApiError && failure.code === "PHOTO_EXISTS") {
          // Already on the bar, maybe from an earlier try whose answer was lost.
          update(next.key, null);
          setMessage("이미 등록된 사진이에요.");
          void actions.refresh();
        } else if (failure instanceof ApiError && failure.code === "PHOTO_LIMIT_REACHED") {
          // The bar is full: the photos still waiting stop too.
          setQueue((current) =>
            current.map((item) => (item.key === next.key || item.status === "waiting" ? { ...item, status: "failed", error: LIMIT_REACHED } : item)),
          );
          void actions.refresh();
        } else {
          update(next.key, { status: "failed", error: uploadMessage(failure) ?? fail(failure) ?? undefined });
        }
      } finally {
        running.current = false;
      }
    })();
  }, [queue, busy, actions, update, fail]);

  // The previews are released with the page.
  const previews = useRef(queue);
  previews.current = queue;
  useEffect(() => () => previews.current.forEach((item) => URL.revokeObjectURL(item.previewUrl)), []);

  function pick(files: File[]) {
    setMessage(null);
    const slots = photoSlots(photos.length, queue.length);
    if (files.length > slots) setMessage(LIMIT);
    const added = files.slice(0, slots).map((file) => ({
      key: nextKey.current++,
      file,
      previewUrl: URL.createObjectURL(file),
      status: "waiting" as const,
    }));
    setQueue((current) => [...current, ...added]);
  }

  async function run(change: () => Promise<unknown>) {
    if (busy || uploading) return;
    setBusy(true);
    setMessage(null);
    setMenuId(null);
    try {
      await change();
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "PHOTOS_OUTDATED") {
        // Changed on another device meanwhile: show the photos as they are now, to sort again.
        const current = failure.details?.photos;
        if (Array.isArray(current)) await actions.show(current as BarPhoto[]);
        else await actions.refresh();
        setMessage("다른 곳에서 사진이 바뀌었어요. 다시 정렬해 주세요.");
      } else if (failure instanceof ApiError && failure.code === "PHOTO_NOT_FOUND") {
        await actions.refresh();
        setMessage("이미 삭제된 사진이에요.");
      } else {
        setMessage(fail(failure));
      }
    } finally {
      setBusy(false);
    }
  }

  const reorder = (order: BarPhoto[]) => run(() => actions.reorder(order.map((photo) => photo.photoId)));

  function askDelete(photoId: string) {
    setMenuId(null);
    // OwnerPhotoHtmlV4Screen.kt: the last photo stays.
    if (!canDeletePhoto(photos.length)) return setMessage("마지막 사진은 삭제할 수 없어요.");
    setDeleteId(photoId);
  }

  function confirmDelete() {
    const photoId = deleteId;
    setDeleteId(null);
    if (photoId) void run(() => actions.remove(photoId));
  }

  const locked = busy || uploading;
  const full = photoSlots(photos.length, queue.length) === 0;
  return (
    <div className={styles.screen}>
      <div className={styles.sectionHead}>
        <p className={styles.hint}>
          {photos.length}/15장. 첫 사진이 대표 사진이에요. 바꾸면 바로 저장돼요.
        </p>
        <label className={[styles.addPhoto, full ? styles.addPhotoOff : ""].join(" ")}>
          + 사진 추가
          <input
            type="file"
            accept="image/*"
            multiple
            className={styles.fileInput}
            disabled={full}
            onChange={(event) => {
              pick(Array.from(event.currentTarget.files ?? []));
              event.currentTarget.value = "";
            }}
          />
        </label>
      </div>

      {photos.length === 0 && queue.length === 0 ? <p className={styles.hint}>등록된 사진이 없습니다. 사진을 추가해 주세요.</p> : null}

      <ul className={styles.photoGrid} aria-label="매장 사진">
        {photos.map((photo, index) => (
          <li key={photo.photoId} className={styles.photoTile} aria-label={index === 0 ? "대표 사진" : `사진 ${index + 1}`}>
            <button
              type="button"
              className={styles.photoButton}
              aria-label={`${index === 0 ? "대표 사진" : `사진 ${index + 1}`} 메뉴`}
              aria-expanded={menuId === photo.photoId}
              disabled={locked}
              onClick={() => setMenuId(menuId === photo.photoId ? null : photo.photoId)}
            >
              <img src={photo.thumbnailUrl} alt="" loading="lazy" />
              {index === 0 ? <span className={styles.coverBadge}>대표</span> : null}
            </button>
            {menuId === photo.photoId ? (
              <div className={styles.photoMenu}>
                {index > 0 ? (
                  <Button variant="text" onClick={() => void reorder(makeCover(photos, index))}>
                    대표 사진 등록
                  </Button>
                ) : null}
                <Button variant="text" className={styles.danger} onClick={() => askDelete(photo.photoId)}>
                  삭제하기
                </Button>
                <Button variant="text" onClick={() => setMenuId(null)}>
                  닫기
                </Button>
              </div>
            ) : null}
            <div className={styles.actions}>
              <Button
                variant="secondary"
                aria-label={`사진 ${index + 1} 앞으로`}
                disabled={locked || index <= 1}
                onClick={() => void reorder(moveSecondaryPhoto(photos, index, -1))}
              >
                ←
              </Button>
              <Button
                variant="secondary"
                aria-label={`사진 ${index + 1} 뒤로`}
                disabled={locked || index === 0 || index >= photos.length - 1}
                onClick={() => void reorder(moveSecondaryPhoto(photos, index, 1))}
              >
                →
              </Button>
            </div>
          </li>
        ))}
        {queue.map((item) => (
          <li key={item.key} className={styles.photoTile} aria-label={`올리는 사진 ${item.file.name}`}>
            <div className={styles.photoButton}>
              <img src={item.previewUrl} alt="" />
            </div>
            {item.status === "failed" ? (
              <>
                <p className={styles.error} role="alert">
                  {item.error ?? "사진을 올리지 못했어요."}
                </p>
                <div className={styles.actions}>
                  <Button variant="secondary" disabled={item.error === LIMIT_REACHED && full} onClick={() => update(item.key, { status: "waiting", error: undefined })}>
                    다시 시도
                  </Button>
                  <Button variant="secondary" onClick={() => update(item.key, null)}>
                    빼기
                  </Button>
                </div>
              </>
            ) : (
              <p className={styles.hint} role="status">
                {item.status === "uploading" ? "올리는 중" : "기다리는 중"}
              </p>
            )}
          </li>
        ))}
      </ul>

      {message ? (
        <p className={styles.error} role="alert">
          {message}
        </p>
      ) : null}
      <ButtonLink to={`/bars/${bar.barId}/info`} variant="primary">
        완료
      </ButtonLink>

      <BottomSheet open={deleteId !== null} title="사진을 삭제할까요?" onClose={() => setDeleteId(null)}>
        <p className={styles.sheetText}>삭제한 사진은 고객 화면에서도 바로 사라집니다.</p>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={() => setDeleteId(null)}>
            취소
          </Button>
          <Button onClick={confirmDelete}>삭제하기</Button>
        </div>
      </BottomSheet>

      <BottomSheet open={guard.asking} title="변경을 취소할까요?" onClose={guard.stay}>
        {/* OwnerInfoHtmlV4Screen.kt's discard sheet; here the unsaved changes are photos not uploaded yet. */}
        <p className={styles.sheetText}>저장하지 않은 수정 사항은 사라집니다.</p>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={guard.stay}>
            계속 편집
          </Button>
          <Button onClick={guard.leave}>변경 취소</Button>
        </div>
      </BottomSheet>
    </div>
  );
}
