import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/errors";
import type { useImportActions } from "../importApi";
import { clearDeviceDraft, draftBytes, encodeDraft, MAX_DRAFT_BYTES, writeDeviceDraft } from "./draft";
import type { ReviewState } from "./model";

/**
 * Where the review draft is (spec 5.9):
 * - `saved`: on the server; `saving`: on its way.
 * - `device`: the server could not be reached, so it is kept on this device and sent again.
 * - `tooLarge`: over 256 KB, kept on this device only.
 * - `conflict`: someone saved another draft first (409 REVIEW_DRAFT_OUTDATED); the owner chooses which to keep.
 * - `closed`: the import is no longer in review (409 INVALID_IMPORT_STATE).
 */
export type DraftStatus = "idle" | "saving" | "saved" | "device" | "tooLarge" | "conflict" | "closed";

/** As the app does after each change, a little later so typing is not sent key by key. */
const SAVE_DELAY_MS = 1_000;

interface DraftSyncOptions {
  menuImportId: string;
  reviewVersion: number;
  userId: string;
  /** The server draft version the screen's cards start from (0 without one). */
  baseDraftVersion: number;
  actions: ReturnType<typeof useImportActions>;
  /** The import left review; the screen reads it again. */
  onClosed: () => void;
  /** 403 and 404: the message to show, as every bar change shows them. */
  onFailure: (failure: unknown) => void;
}

/**
 * Saves the review as a draft after each change, one request at a time and always the latest cards, keeping a copy
 * on this device until the server has it (PhotoReviewViewModel.kt `saveDraft`, PendingReviewDraftStore.kt).
 */
export function useDraftSync({ menuImportId, reviewVersion, userId, baseDraftVersion, actions, onClosed, onFailure }: DraftSyncOptions) {
  const [status, setStatus] = useState<DraftStatus>("idle");
  const base = useRef(baseDraftVersion);
  const latest = useRef<ReviewState | null>(null);
  const dirty = useRef(false);
  const running = useRef<Promise<void> | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statusRef = useRef<DraftStatus>("idle");
  const conflictVersion = useRef<number | null>(null);
  const callbacks = useRef({ onClosed, onFailure });
  callbacks.current = { onClosed, onFailure };

  const update = useCallback((next: DraftStatus) => {
    statusRef.current = next;
    setStatus(next);
  }, []);

  const keepOnDevice = useCallback(
    (state: ReviewState) => writeDeviceDraft(userId, menuImportId, { reviewVersion, baseDraftVersion: base.current, content: encodeDraft(state) }),
    [menuImportId, reviewVersion, userId],
  );

  const sendOnce = useCallback(async () => {
    const state = latest.current;
    if (!state || !dirty.current) return;
    if (statusRef.current === "conflict" || statusRef.current === "closed" || statusRef.current === "tooLarge") return;
    const content = encodeDraft(state);
    if (draftBytes(content) > MAX_DRAFT_BYTES) return update("tooLarge");
    dirty.current = false;
    update("saving");
    try {
      const saved = await actions.saveDraft(menuImportId, { draftVersion: base.current, reviewVersion, content });
      base.current = saved.draftVersion;
      if (dirty.current && latest.current) keepOnDevice(latest.current);
      else clearDeviceDraft(userId, menuImportId);
      update("saved");
    } catch (failure) {
      dirty.current = true;
      const code = failure instanceof ApiError ? failure.code : null;
      if (code === "REVIEW_DRAFT_OUTDATED") {
        const current = failure instanceof ApiError ? failure.details?.currentDraftVersion : null;
        conflictVersion.current = typeof current === "number" ? current : null;
        update("conflict");
      } else if (code === "REVIEW_DRAFT_TOO_LARGE") update("tooLarge");
      else if (code === "INVALID_IMPORT_STATE" || code === "MENU_IMPORT_NOT_FOUND") {
        update("closed");
        callbacks.current.onClosed();
      } else if (code === "FORBIDDEN" || code === "BAR_NOT_FOUND") {
        update("device");
        callbacks.current.onFailure(failure);
      } else update("device");
    }
  }, [actions, keepOnDevice, menuImportId, reviewVersion, update, userId]);

  /** Sends until the latest cards are on the server, or a failure stops it. */
  const drain = useCallback((): Promise<void> => {
    running.current ??= (async () => {
      try {
        while (dirty.current && (statusRef.current === "idle" || statusRef.current === "saved" || statusRef.current === "saving")) await sendOnce();
      } finally {
        running.current = null;
      }
    })();
    return running.current;
  }, [sendOnce]);

  /** The cards changed: kept on this device at once, sent shortly. */
  const schedule = useCallback(
    (state: ReviewState) => {
      latest.current = state;
      dirty.current = true;
      keepOnDevice(state);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void drain(), SAVE_DELAY_MS);
    },
    [drain, keepOnDevice],
  );

  /** Sends what is waiting now (before leaving or publishing) and tells where the draft ended up. */
  const flush = useCallback(async (): Promise<DraftStatus> => {
    if (timer.current) clearTimeout(timer.current);
    await running.current;
    await drain();
    return statusRef.current;
  }, [drain]);

  /** "다시 시도" after the server could not be reached. */
  const retry = useCallback(() => {
    if (statusRef.current !== "device") return;
    update("idle");
    void drain();
  }, [drain, update]);

  /** "이 기기 내용으로 덮어쓰기": saved over the other draft, from its version (5.9). */
  const overwrite = useCallback(
    (serverDraftVersion?: number) => {
      base.current = serverDraftVersion ?? conflictVersion.current ?? base.current;
      dirty.current = true;
      if (latest.current) keepOnDevice(latest.current);
      update("idle");
      void drain();
    },
    [drain, keepOnDevice, update],
  );

  /** The draft is done with: applied, canceled, or replaced by the other draft. */
  const discard = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    dirty.current = false;
    clearDeviceDraft(userId, menuImportId);
  }, [menuImportId, userId]);

  useEffect(
    () => () => {
      // Leaving the screen sends what is waiting; the device copy stays until the server has it.
      if (timer.current) clearTimeout(timer.current);
      if (dirty.current) void drain();
    },
    [drain],
  );

  return { status, schedule, flush, retry, overwrite, discard };
}
