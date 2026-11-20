import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router";
import { errorMessage } from "../api/errors";
import { clearReturnPath, readReturnPath } from "../auth/returnPath";
import { useSession } from "../auth/SessionProvider";
import { ownerEntry } from "../owner/entry";
import { useMe, useMyApplications, useMyBars, type OwnedBar } from "../owner/queries";
import { AppShell } from "../ui/AppShell";
import { Button, ButtonLink } from "../ui/Button";
import { EmptyState, ErrorState, LoadingState } from "../ui/states";
import styles from "./pages.module.css";

/** A signed-in screen in the app frame, with the account from GET /api/me. */
function OwnerScreen({ title, backTo, children }: { title: string; backTo?: string; children: React.ReactNode }) {
  const me = useMe();
  return (
    <AppShell title={title} backTo={backTo} account={me.data?.email ?? me.data?.displayName}>
      {children}
    </AppShell>
  );
}

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
  switch (ownerEntry(bars.data?.items, applications.data?.items)) {
    case "loading":
      return <LoadingState message="매장 상태를 확인하고 있어요." />;
    case "bars":
      return <Navigate to="/bars" replace />;
    case "application":
      return <Navigate to="/applications" replace />;
    case "apply":
      return <Navigate to="/apply" replace />;
  }
}

function ComingSoon({ title, description }: { title: string; description: string }) {
  return (
    <OwnerScreen title={title}>
      <EmptyState title="준비 중이에요" description={description} />
    </OwnerScreen>
  );
}

// Placeholders: the screens themselves come in later tasks (P11, P16, P22 and on).
export function ApplicationStatusPage() {
  return <ComingSoon title="등록 신청 상태" description="신청 상태를 곧 웹에서도 확인할 수 있어요." />;
}

export function BarsPage() {
  return <ComingSoon title="내 매장" description="관리하는 매장 목록을 곧 웹에서도 볼 수 있어요." />;
}

export function BarHomePage({ bar }: { bar: OwnedBar }) {
  return (
    <OwnerScreen title={bar.name} backTo="/bars">
      <EmptyState title="준비 중이에요" description="매장 관리 기능을 곧 웹에서도 쓸 수 있어요." />
    </OwnerScreen>
  );
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
