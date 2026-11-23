import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { unwrap } from "../api/client";
import { ApiError } from "../api/errors";
import { useSession } from "../auth/SessionProvider";
import { ownerQueryKeys, type BarDetail, type BarMenu } from "../owner/queries";

/**
 * One request at a time, with `pending` for the screen to lock. A second call while one runs is ignored
 * (resolves null).
 */
function useOneAtATime() {
  const [pending, setPending] = useState(false);
  const busy = useRef(false);
  async function run<T>(task: () => Promise<T>): Promise<T | null> {
    if (busy.current) return null;
    busy.current = true;
    setPending(true);
    try {
      return await task();
    } finally {
      busy.current = false;
      setPending(false);
    }
  }
  return { run, pending };
}

/**
 * PUT /api/bars/{barId}/menu/items/{barMenuItemId}/sold-out (spec 3.14.8), as the app's `setSoldOutLive`:
 * `{soldOut}` alone, without `menuVersion`, and not held back by an unfinished import. The answer (the whole
 * menu, as 3.9) is shown at once and the menu read again. The request sets a value, so the same request sent
 * again after a lost answer gives the same result. MENU_ITEM_NOT_FOUND reads the menu again.
 */
export function useSoldOut(barId: string) {
  const { api } = useSession();
  const queryClient = useQueryClient();
  const { run, pending } = useOneAtATime();
  const reloadMenu = () => queryClient.invalidateQueries({ queryKey: ownerQueryKeys.menu(barId), refetchType: "all" });

  const send = (barMenuItemId: string, soldOut: boolean) =>
    run(async () => {
      try {
        const menu: BarMenu = unwrap(
          await api.PUT("/api/bars/{barId}/menu/items/{barMenuItemId}/sold-out", {
            params: { path: { barId, barMenuItemId } },
            body: { soldOut },
          }),
        );
        queryClient.setQueryData(ownerQueryKeys.menu(barId), menu);
        await reloadMenu();
        return menu;
      } catch (failure) {
        if (failure instanceof ApiError && failure.code === "MENU_ITEM_NOT_FOUND") void reloadMenu();
        throw failure;
      }
    });
  return { send, pending };
}

/**
 * POST /api/bars/{barId}/menu/confirm (spec 3.14.9), the home's "지금도 맞아요", as the app's
 * `confirmMenuInformationLive`, but with the `menuVersion` of the menu the owner sees, not the newest one.
 * The answer (the bar, as 3.6) is shown at once; the bar and the bar list are read again.
 * MENU_OUTDATED and NO_PUBLISHED_MENU read the menu and the bar again, so the card shows the menu as it is.
 * Confirming changes no menu, so sending it again after a lost answer is safe.
 */
export function useConfirmMenu(barId: string) {
  const { api } = useSession();
  const queryClient = useQueryClient();
  const { run, pending } = useOneAtATime();
  const reload = (keys: readonly (readonly unknown[])[]) =>
    Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey, refetchType: "all" })));

  const send = (menuVersion: number | null) =>
    run(async () => {
      try {
        const bar: BarDetail = unwrap(await api.POST("/api/bars/{barId}/menu/confirm", { params: { path: { barId } }, body: { menuVersion } }));
        queryClient.setQueryData(ownerQueryKeys.bar(barId), bar);
        await reload([ownerQueryKeys.bar(barId), ownerQueryKeys.myBars]);
        return bar;
      } catch (failure) {
        if (failure instanceof ApiError && (failure.code === "MENU_OUTDATED" || failure.code === "NO_PUBLISHED_MENU")) {
          void reload([ownerQueryKeys.menu(barId), ownerQueryKeys.bar(barId)]);
        }
        throw failure;
      }
    });
  return { send, pending };
}
