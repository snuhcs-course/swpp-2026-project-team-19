import type { ReactNode } from "react";
import { AppShell } from "../ui/AppShell";
import { useMe } from "./queries";

/** A signed-in screen in the app frame, with the account from GET /api/me. */
export function OwnerScreen({ title, backTo, children }: { title: string; backTo?: string; children: ReactNode }) {
  const me = useMe();
  return (
    <AppShell title={title} backTo={backTo} account={me.data?.email ?? me.data?.displayName}>
      {children}
    </AppShell>
  );
}
