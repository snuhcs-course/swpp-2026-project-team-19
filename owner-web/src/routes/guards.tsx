import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation, useParams } from "react-router";
import { useSession } from "../auth/SessionProvider";
import { useMe, useMyBars, type OwnedBar } from "../owner/queries";
import { ErrorState, LoadingState } from "../ui/states";
import { QueryView } from "../ui/QueryView";
import { ButtonLink } from "../ui/Button";

/**
 * Every screen but sign-in: a signed-out visitor goes to sign-in, and the start screen sends them back here
 * afterwards (EntryPage). Once signed in, GET /api/me runs before anything else, since it creates the users
 * row the other APIs need (spec 3.1.4).
 */
export function RequireSignIn() {
  const { status } = useSession();
  const location = useLocation();

  if (status === "restoring") return <LoadingState message="로그인 정보를 확인하고 있어요." />;
  if (status === "signedOut") {
    // The start screen is where every sign-in ends anyway, so it is not passed on: a destination saved
    // before a failed Google sign-in (which returns to /owner/) stays for the next attempt.
    const from = location.pathname + location.search;
    return <Navigate to="/login" replace state={from === "/" ? null : { from }} />;
  }
  return <SignedIn />;
}

function SignedIn() {
  const me = useMe();
  return (
    <QueryView query={me} loadingMessage="계정 정보를 불러오고 있어요.">
      {() => <Outlet />}
    </QueryView>
  );
}

/**
 * A bar's screens are only for its current owner. The server checks every request too (403); this keeps a
 * signed-in user who does not own the bar from seeing its screens at all (P10).
 */
export function RequireOwnedBar({ children }: { children: (bar: OwnedBar) => ReactNode }) {
  const { barId } = useParams();
  const bars = useMyBars();
  return (
    // A failed refetch keeps the bar's screens (and any unsaved input) as they were; a successful one that
    // no longer lists the bar closes them.
    <QueryView query={bars} loadingMessage="매장 정보를 불러오고 있어요." keepDataOnRefetchError>
      {(data) => {
        const bar = data.items.find((item) => item.barId === barId);
        if (!bar) return <NoAccess />;
        return children(bar);
      }}
    </QueryView>
  );
}

export function NoAccess() {
  return (
    <ErrorState
      message="이 매장을 관리할 권한이 없어요."
      action={
        <ButtonLink to="/">처음 화면으로</ButtonLink>
      }
    />
  );
}
