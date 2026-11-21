import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router";
import { errorMessage } from "../api/errors";
import { clearReturnPath, readReturnPath } from "../auth/returnPath";
import { useSession } from "../auth/SessionProvider";
import { hasPhotosToSend, loadDraft } from "../application/draft";
import { ownerEntry } from "../owner/entry";
import { loadHiddenApplications } from "../owner/hiddenApplications";
import { OwnerScreen } from "../owner/OwnerScreen";
import { useMe, useMyApplications, useMyBars } from "../owner/queries";
import { Button, ButtonLink } from "../ui/Button";
import { EmptyState, ErrorState, LoadingState } from "../ui/states";
import styles from "./pages.module.css";

export function LoginPage() {
  const { status, configured, notice, signIn } = useSession();
  const location = useLocation();
  const from = (location.state as { from?: unknown } | null)?.from;
  const returnPath = typeof from === "string" ? from : undefined;

  if (status === "signedIn") return <Navigate to={returnPath ?? "/"} replace />;
  if (status === "restoring") return <LoadingState message="로그인 정보를 확인하고 있어요." />;
  return (
    <main className={styles.login}>
      <h1 className={styles.loginTitle}>BottleMap 사장님</h1>
      <p className={styles.loginText}>
        안드로이드 앱의 매장 관리 기능을 웹에서 쓸 수 있어요. 앱과 같은 Google 계정으로 로그인해 주세요.
      </p>
      {notice ? (
        <p className={styles.notice} role="alert">
          {notice}
        </p>
      ) : null}
      {configured ? null : (
        <p className={styles.notice} role="alert">
          지금은 로그인할 수 없어요. 잠시 후 다시 시도해 주세요.
        </p>
      )}
      <Button disabled={!configured} onClick={() => void signIn(returnPath)}>
        Google로 로그인
      </Button>
    </main>
  );
}

/**
 * /owner/, where every Google sign-in returns: continues to the page the owner was going to before signing in,
 * or else sends them to bars, application status or a new application (src/owner/entry.ts). Deciding both
 * here keeps a single redirect, so the two can never race.
 */
export function EntryPage() {
  const me = useMe();
  const bars = useMyBars();
  const applications = useMyApplications();
  // Read once: the stored copy is removed below, and a later render (e.g. when the bars arrive) must still
  // redirect to the same page rather than fall through to the status screens.
  const [returnPath] = useState(readReturnPath);
  useEffect(() => {
    if (returnPath) clearReturnPath();
  }, [returnPath]);
  if (returnPath) return <Navigate to={returnPath} replace />;

  const failed = bars.error ?? applications.error;
  if (failed) {
    return (
      <OwnerScreen title="내 매장">
        <ErrorState
          message={errorMessage(failed)}
          retrying={bars.isFetching || applications.isFetching}
          onRetry={() => {
            if (bars.isError) void bars.refetch();
            if (applications.isError) void applications.refetch();
          }}
        />
      </OwnerScreen>
    );
  }
  switch (ownerEntry(bars.data?.items, applications.data?.items, loadHiddenApplications(me.data?.userId))) {
    case "loading":
      return <LoadingState message="매장 상태를 확인하고 있어요." />;
    case "bars":
      return <Navigate to="/bars" replace />;
    case "application":
      // An application sent from this browser whose photos failed to upload: only the form can send them.
      if (me.isPending) return <LoadingState message="매장 상태를 확인하고 있어요." />;
      if (me.data && hasPhotosToSend(loadDraft(me.data.userId), applications.data?.items ?? [])) {
        return <Navigate to="/apply" replace />;
      }
      return <Navigate to="/applications" replace />;
    case "apply":
      return <Navigate to="/apply" replace />;
  }
}

export function NotFoundPage() {
  return (
    <main className={styles.login}>
      <EmptyState
        title="페이지를 찾을 수 없어요"
        action={
          <ButtonLink to="/">처음 화면으로</ButtonLink>
        }
      />
    </main>
  );
}
