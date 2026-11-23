import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useLocation, useParams } from "react-router";
import { ApiError } from "../api/errors";
import { OwnerScreen } from "../owner/OwnerScreen";
import { useBar, useBarMenu, type OwnedBar } from "../owner/queries";
import { Button, ButtonLink } from "../ui/Button";
import { ErrorState, LoadingState } from "../ui/states";
import { QueryView } from "../ui/QueryView";
import { importPath } from "./ImportEntry";
import { ImportSteps } from "./ImportStartPage";
import { MAX_POLLS, useImportActions, useMenuImport, type ImportStatusResponse } from "./importApi";
import styles from "./menuImport.module.css";

// The review is the largest screen; it loads only when an import is ready for it.
const ReviewScreen = lazy(() => import("./review/ReviewScreen").then((module) => ({ default: module.ReviewScreen })));

/** What a screen left to say when it came here (an import continued instead of a new upload, for example). */
export interface ImportNotice {
  notice?: string;
}

/**
 * /owner/bars/:barId/menu/import/:menuImportId: one menu import, drawn from the server's state only (spec 5.1),
 * so a reload or another tab shows the same screen. While it is processing it is read again every 2 seconds, 180
 * times at most (spec 4.2); once ready it opens the review (5.4).
 */
export function ImportJobPage({ bar }: { bar: OwnedBar }) {
  const { menuImportId = "" } = useParams();
  const location = useLocation();
  const [notice, setNotice] = useState<string | null>((location.state as ImportNotice | null)?.notice ?? null);
  const [polls, setPolls] = useState(0);
  const query = useMenuImport(menuImportId, polls < MAX_POLLS);
  const actions = useImportActions(bar.barId);
  const status = query.data?.status;
  const processing = status === "uploaded" || status === "processing";

  // Each answer while processing counts toward the 180 reads.
  useEffect(() => {
    if (processing) setPolls((count) => count + 1);
  }, [query.dataUpdatedAt, processing]);
  // When the import leaves processing, the bar's `activeMenuImport` (the menu lock) and the import row change.
  const lastStatus = useRef(status);
  useEffect(() => {
    if (lastStatus.current !== undefined && lastStatus.current !== status) void actions.refreshBar();
    lastStatus.current = status;
  }, [status, actions]);

  const backTo = `/bars/${bar.barId}/menu`;
  const notFound = query.error instanceof ApiError && query.error.code === "MENU_IMPORT_NOT_FOUND";
  const otherBar = query.data && "barId" in query.data && query.data.barId !== bar.barId;
  return (
    <OwnerScreen title={status === "ready_for_review" ? "메뉴 검수" : "메뉴판 사진 등록"} backTo={backTo}>
      {notice ? (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      ) : null}
      {notFound || otherBar ? (
        // Spec 5.1 sends a missing import to the import list; the menu screen holds the web's.
        <ErrorState message="메뉴판 작업을 찾을 수 없어요." action={<ButtonLink to={backTo}>메뉴 관리로</ButtonLink>} />
      ) : (
        <QueryView query={query} loadingMessage="메뉴판 작업을 불러오고 있어요." keepDataOnRefetchError>
          {(data) => (
            <ImportState
              bar={bar}
              data={data}
              slow={processing && polls >= MAX_POLLS}
              readFailed={query.isError}
              retry={() => {
                setPolls(0);
                void query.refetch();
              }}
              onNotice={setNotice}
            />
          )}
        </QueryView>
      )}
    </OwnerScreen>
  );
}

function ImportState({
  bar,
  data,
  slow,
  readFailed,
  retry,
  onNotice,
}: {
  bar: OwnedBar;
  data: ImportStatusResponse;
  slow: boolean;
  readFailed: boolean;
  retry: () => void;
  onNotice: (message: string | null) => void;
}) {
  const menuPath = `/bars/${bar.barId}/menu`;
  const home = (
    <ButtonLink to={`/bars/${bar.barId}`} variant="secondary">
      내 매장으로 돌아가기
    </ButtonLink>
  );
  switch (data.status) {
    case "uploaded":
    case "processing": {
      const { totalImages, completedImages } = data.progress;
      const percent = totalImages > 0 ? Math.round((completedImages / totalImages) * 100) : 0;
      return (
        <div className={styles.screen}>
          <ImportSteps step={1} />
          <div>
            <h2 className={styles.title}>메뉴판 분석 중</h2>
            <p className={styles.text}>다른 작업도 할 수 있어요.</p>
          </div>
          <p className={styles.strong} role="status">
            사진 {totalImages}장 중 {completedImages}장을 읽었어요
          </p>
          {/* 5.2: the count guides the owner only; matching continues after the last photo. */}
          <div className={styles.progress} role="progressbar" aria-label="메뉴판 분석" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
            <span style={{ width: `${percent}%` }} />
          </div>
          {slow ? <p className={styles.notice}>분석 시간이 길어지고 있어요. 나갔다가 다시 확인해 주세요.</p> : null}
          {readFailed ? (
            <div className={styles.row}>
              <p className={styles.error} role="alert">
                메뉴판 분석 상태를 불러오지 못했어요.
              </p>
              <Button variant="secondary" onClick={retry}>
                다시 시도
              </Button>
            </div>
          ) : null}
          <div className={styles.actions}>{home}</div>
        </div>
      );
    }
    case "failed":
      return (
        <div className={styles.screen}>
          <ImportSteps step={1} />
          <h2 className={styles.title}>메뉴판을 읽지 못했어요</h2>
          {/* Spec 5.3: the server's message (the app shows its own fixed text, data/android 수정 필요 사항.md). */}
          <p className={styles.strong} role="alert">
            {data.failure.message}
          </p>
          <p className={styles.text}>
            사진 {data.progress.totalImages}장 중 {data.progress.completedImages}장을 읽었어요. 원래 게시된 메뉴는 변경되지 않았어요.
          </p>
          <div className={styles.actions}>
            <ButtonLink to={importPath(bar.barId)} variant="primary">
              사진 다시 올리기
            </ButtonLink>
            {home}
          </div>
        </div>
      );
    case "canceled":
      return (
        <div className={styles.screen}>
          <h2 className={styles.title}>작업이 취소됐어요</h2>
          <p className={styles.text}>원래 게시된 메뉴는 변경되지 않았어요. 새 메뉴판 사진을 올릴 수 있어요.</p>
          <div className={styles.actions}>
            <ButtonLink to={importPath(bar.barId)} variant="primary">
              새 메뉴판 사진 올리기
            </ButtonLink>
            <ButtonLink to={menuPath}>메뉴 관리로</ButtonLink>
          </div>
        </div>
      );
    case "applied":
      return (
        <div className={styles.screen}>
          <h2 className={styles.title}>이미 게시된 작업이에요</h2>
          <p className={styles.text}>메뉴 관리에서 게시된 메뉴를 확인할 수 있어요.</p>
          <div className={styles.actions}>
            <ButtonLink to={menuPath} variant="primary">
              메뉴 관리로
            </ButtonLink>
          </div>
        </div>
      );
    case "ready_for_review":
      return <ReviewLoader bar={bar} review={data} onNotice={onNotice} />;
  }
}

/** The review needs the bar's current menu (its prices, 3.9) and default pour (3.6) besides the review itself. */
function ReviewLoader({ bar, review, onNotice }: { bar: OwnedBar; review: Extract<ImportStatusResponse, { status: "ready_for_review" }>; onNotice: (message: string | null) => void }) {
  const menu = useBarMenu(bar.barId);
  const detail = useBar(bar.barId);
  if (menu.isError || detail.isError) {
    return (
      <ErrorState
        message="검수 정보를 불러오지 못했어요. 다시 시도해 주세요."
        onRetry={() => {
          if (menu.isError) void menu.refetch();
          if (detail.isError) void detail.refetch();
        }}
        retrying={menu.isFetching || detail.isFetching}
      />
    );
  }
  if (!menu.data || !detail.data) return <LoadingState message="검수 정보를 불러오고 있어요." />;
  return (
    <Suspense fallback={<LoadingState message="검수 화면을 여는 중이에요." />}>
      {/* A review built again (a new reviewVersion, 9.4) starts over from its draft. */}
      <ReviewScreen key={review.reviewVersion} review={review} menu={menu.data} bar={detail.data} onNotice={onNotice} />
    </Suspense>
  );
}
