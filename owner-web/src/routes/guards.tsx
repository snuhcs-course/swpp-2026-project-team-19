import { useEffect, useRef, type ReactNode } from "react";
import { Navigate, Outlet, useLocation, useNavigate, useParams } from "react-router";
import { takeReturnPath } from "../auth/returnPath";
import { useSession } from "../auth/SessionProvider";
import { useMe, useMyBars, type OwnedBar } from "../owner/queries";
import { ErrorState, LoadingState } from "../ui/states";
import { QueryView } from "../ui/QueryView";
import { ButtonLink } from "../ui/Button";

/**
 * Every screen but sign-in: a signed-out visitor goes to sign-in and comes back here afterwards. Once signed
 * in, GET /api/me runs before anything else, since it creates the users row the other APIs need (spec 3.1.4).
 */
export function RequireSignIn() {
  const { status } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const returned = useRef(false);

  // After the Google round trip the page restarts at /owner/; continue to where the owner was going.
  useEffect(() => {
    if (status !== "signedIn" || returned.current) return;
    returned.current = true;
    const path = takeReturnPath();
    if (path && path !== location.pathname + location.search) void navigate(path, { replace: true });
  }, [status, location.pathname, location.search, navigate]);

  if (status === "restoring") return <LoadingState message="로그인 정보를 확인하고 있어요." />;
  if (status === "signedOut") {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
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
    <QueryView query={bars} loadingMessage="매장 정보를 불러오고 있어요.">
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
