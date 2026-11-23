import { useState } from "react";
import { Link } from "react-router";
import { ApiError } from "../api/errors";
import { useBarFailure } from "../bar/failures";
import type { BarDetail } from "../owner/queries";

type ImportBar = Pick<BarDetail, "barId" | "activeMenuImport">;
import { BottomSheet } from "../ui/BottomSheet";
import { Button } from "../ui/Button";
import { isActiveStatus, useImportActions, useLatestImport, type ImportStatus } from "./importApi";
import styles from "./menuImport.module.css";
import barStyles from "../bar/bar.module.css";

/** The import the screens show: the unfinished one (3.6), or else the latest when it failed (3.8), as the app does. */
export function useCurrentImport(bar: ImportBar): { menuImportId: string; status: ImportStatus } | null {
  const latest = useLatestImport(bar.barId);
  if (bar.activeMenuImport) return bar.activeMenuImport;
  const last = latest.data;
  return last && last.status === "failed" ? { menuImportId: last.menuImportId, status: last.status } : null;
}

/** OwnerManagementHomeState.kt `ownerJobTitle` and `ownerJobDescription`. */
export function importTitle(status: ImportStatus): [string, string] {
  switch (status) {
    case "uploaded":
      return ["사진 업로드 완료", "업로드된 사진의 분석을 기다리고 있어요"];
    case "processing":
      return ["AI 분석 중", "다른 작업을 계속할 수 있어요"];
    case "ready_for_review":
      return ["메뉴판 확인 준비 완료", "추가할 메뉴를 확인해 주세요"];
    case "failed":
      return ["메뉴판 분석 실패", "작업을 확인해 주세요"];
    case "applied":
      return ["게시 완료", "메뉴가 게시됐어요"];
    case "canceled":
      return ["작업 취소됨", "새 작업을 시작할 수 있어요"];
  }
}

/** OwnerManualMenuScreen.kt's "사진으로 메뉴 추가" row text, with a comma for the app's middle dot. */
function menuRowText(status: ImportStatus | undefined): string {
  switch (status) {
    case "uploaded":
    case "processing":
      return "메뉴판 분석 중, 작업 확인하기";
    case "ready_for_review":
      return "메뉴 검수 이어서 하기";
    case "failed":
      return "메뉴판 분석 실패, 다시 확인하기";
    default:
      return "메뉴판 사진으로 추가하기";
  }
}

export const importPath = (barId: string, menuImportId?: string) => `/bars/${barId}/menu/import${menuImportId ? `/${menuImportId}` : ""}`;

/**
 * The menu screen's "사진으로 메뉴 추가" row (OwnerManualMenuScreen.kt): it opens the current import, or the
 * photo picker when there is none. An unfinished import can be canceled here after asking (spec 5.7); a failed one
 * is already over, so it has no cancel (the app shows one and the server refuses it).
 */
export function MenuImportRow({ bar, onNotice }: { bar: ImportBar; onNotice: (message: string) => void }) {
  const current = useCurrentImport(bar);
  const actions = useImportActions(bar.barId);
  const fail = useBarFailure();
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);

  async function cancel() {
    if (!current || busy) return;
    setBusy(true);
    try {
      await actions.cancel(current.menuImportId);
      setAsking(false);
    } catch (failure) {
      // A lost or refused answer is not a cancellation: the import is left as it is.
      setAsking(false);
      await actions.refreshBar();
      if (failure instanceof ApiError && failure.code === "NETWORK_ERROR") onNotice("작업 취소에 실패했어요. 인터넷 연결을 확인해 주세요.");
      else if (failure instanceof ApiError && (failure.code === "INVALID_IMPORT_STATE" || failure.code === "MENU_IMPORT_NOT_FOUND")) {
        onNotice("작업 취소에 실패했어요. 메뉴 등록 상태를 확인해 주세요.");
      } else {
        const message = fail(failure);
        if (message) onNotice(message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="사진으로 메뉴 추가">
      <h2 className={styles.strong}>사진으로 메뉴 추가</h2>
      <div className={styles.entry}>
        <Link to={importPath(bar.barId, current?.menuImportId)} className={styles.entryLink}>
          {menuRowText(current?.status)}
        </Link>
        {current && isActiveStatus(current.status) ? (
          <button type="button" className={styles.entryCancel} disabled={busy} onClick={() => setAsking(true)}>
            취소하기
          </button>
        ) : null}
        <span aria-hidden="true">›</span>
      </div>
      <BottomSheet open={asking} title="메뉴판 사진 등록을 취소할까요?" onClose={() => !busy && setAsking(false)}>
        <p className={barStyles.sheetText}>선택한 사진과 검수한 내용이 모두 삭제돼요.</p>
        <div className={barStyles.actions}>
          <Button variant="secondary" disabled={busy} onClick={() => setAsking(false)}>
            돌아가기
          </Button>
          <Button busy={busy} onClick={() => void cancel()}>
            작업 취소하기
          </Button>
        </div>
      </BottomSheet>
    </section>
  );
}

/** The home menu card's import line (OwnerManagementHomeScreen.kt): shown while an import is unfinished or failed. */
export function HomeImportRow({ bar }: { bar: ImportBar }) {
  const current = useCurrentImport(bar);
  if (!current) return null;
  const [title, description] = importTitle(current.status);
  return (
    <Link to={importPath(bar.barId, current.menuImportId)} className={styles.entry} aria-label={`${title}, 확인`}>
      <span className={styles.entryLink}>
        {title}
        <small>{description}</small>
      </span>
      <span aria-hidden="true">확인 ›</span>
    </Link>
  );
}
