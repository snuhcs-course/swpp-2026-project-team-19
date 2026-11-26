import type { ReactNode } from "react";
import { useNavigate } from "react-router";
import { useSession } from "../auth/SessionProvider";
import { Button } from "./Button";
import { PrivacyFooter } from "./PrivacyPolicyLink";
import styles from "./AppShell.module.css";

interface AppShellProps {
  title: string;
  /** Shows a back button that goes to this path inside the app. */
  backTo?: string;
  /** Shows a back button that runs this instead (e.g. the previous step of a form). */
  onBack?: () => void;
  /** The signed-in account, shown next to sign-out. */
  account?: string | null;
  children: ReactNode;
}

/** The frame of every signed-in screen: a top bar with back, title and sign-out, and a phone-wide column. */
export function AppShell({ title, backTo, onBack, account, children }: AppShellProps) {
  const { signOut } = useSession();
  const navigate = useNavigate();
  return (
    <div className={styles.shell}>
      <header className={styles.bar}>
        {backTo || onBack ? (
          <button
            type="button"
            className={styles.back}
            onClick={() => (onBack ? onBack() : void navigate(backTo ?? "/"))}
            aria-label="뒤로"
          >
            ‹
          </button>
        ) : null}
        <h1 className={styles.title}>{title}</h1>
        <div className={styles.account}>
          {account ? <span className={styles.email}>{account}</span> : null}
          <Button variant="text" onClick={() => void signOut()}>
            로그아웃
          </Button>
        </div>
      </header>
      <main className={styles.main}>{children}</main>
      <PrivacyFooter />
    </div>
  );
}
