import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { unwrap } from "../api/client";
import { ApiError, isRetryable } from "../api/errors";
import { useSession } from "../auth/SessionProvider";
import { ownerQueryKeys, type BarMenu } from "../owner/queries";
import type { MenuOptionInput } from "./menuEditor";
import type { AddIdentity } from "./menuIdentity";
import type { MenuItem } from "./menuRules";

/** One change to the menu (spec 3.14.3 to 3.14.6). */
export type MenuWrite =
  | { kind: "add"; body: { displayName: string; options: MenuOptionInput[] } & AddIdentity }
  | { kind: "edit"; barMenuItemId: string; body: { displayName: string; options: MenuOptionInput[] } }
  | { kind: "delete"; barMenuItemId: string }
  | { kind: "reset" };

const sameInstant = (a: string, b: string) => Date.parse(a) === Date.parse(b);

function sameOptions(saved: MenuItem["options"], sent: MenuOptionInput[]): boolean {
  return (
    saved.length === sent.length &&
    sent.every((option, index) => {
      const stored = saved[index];
      if (!stored) return false;
      const discount = option.discount ?? null;
      return (
        stored.optionLabel === (option.optionLabel?.trim() || null) &&
        stored.pourMl === (option.pourMl ?? null) &&
        stored.priceKrw === option.priceKrw &&
        (discount === null
          ? stored.discount === null
          : stored.discount !== null &&
            stored.discount.discountedPriceKrw === discount.discountedPriceKrw &&
            sameInstant(stored.discount.startsAt, discount.startsAt) &&
            sameInstant(stored.discount.endsAt, discount.endsAt))
      );
    })
  );
}

const sameContent = (item: MenuItem | undefined, body: { displayName: string; options: MenuOptionInput[] }) =>
  item !== undefined && item.displayName === body.displayName.trim() && sameOptions(item.options, body.options);

/**
 * Whether `menu` already holds the change (spec 3.14.1 "재시도": a resent request whose first try succeeded
 * gets MENU_OUTDATED). An add is the item of its product, or the last item for one without a product
 * (3.14.3); an edit is the item with the name and options sent; a delete has no such item; a reset, no items.
 * An edit whose new name linked the item to another product moves it to another `barMenuItemId` (3.14.4):
 * that is not recognized, and the owner saves again.
 */
export function appliedIn(menu: BarMenu, write: MenuWrite): boolean {
  switch (write.kind) {
    case "add": {
      const body = write.body;
      const item =
        "productId" in body ? menu.items.find((entry) => entry.productId === body.productId) : menu.items.at(-1);
      return sameContent(item, body) && ("productId" in body || (item?.productId === null && item.kind === body.kind));
    }
    case "edit":
      return sameContent(
        menu.items.find((entry) => entry.barMenuItemId === write.barMenuItemId),
        write.body,
      );
    case "delete":
      return !menu.items.some((entry) => entry.barMenuItemId === write.barMenuItemId);
    case "reset":
      return menu.items.length === 0;
  }
}

/**
 * Sends menu changes with the `menuVersion` they were made on (spec 3.14.1), one at a time.
 *
 * - Success: the answer (the whole menu, as 3.9) is shown at once; the menu, the bar (its `currentMenu`) and
 *   the owner's bar list are read again.
 * - No answer (network, 5xx): the request is kept. The same change sent again goes with the same
 *   `menuVersion`, so a first try that succeeded answers MENU_OUTDATED; the menu read again then shows
 *   whether it was applied, and if so it counts as done.
 * - MENU_OUTDATED otherwise, or MENU_ITEM_NOT_FOUND: the menu is read again. ACTIVE_IMPORT_EXISTS: the bar
 *   is read again, so the screens lock (3.14.7). The failure is thrown for the screen to show.
 */
export function useMenuWrite(barId: string) {
  const { api } = useSession();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const busy = useRef(false);
  const unanswered = useRef<{ key: string; menuVersion: number | null } | null>(null);

  async function call(write: MenuWrite, menuVersion: number | null): Promise<BarMenu> {
    const path = { barId };
    switch (write.kind) {
      case "add":
        return unwrap(await api.POST("/api/bars/{barId}/menu/items", { params: { path }, body: { menuVersion, ...write.body } }));
      case "edit":
        return unwrap(
          await api.PUT("/api/bars/{barId}/menu/items/{barMenuItemId}", {
            params: { path: { barId, barMenuItemId: write.barMenuItemId } },
            body: { menuVersion: menuVersion ?? 0, ...write.body },
          }),
        );
      case "delete":
        return unwrap(
          await api.DELETE("/api/bars/{barId}/menu/items/{barMenuItemId}", {
            params: { path: { barId, barMenuItemId: write.barMenuItemId }, query: { menuVersion: menuVersion ?? 0 } },
          }),
        );
      case "reset":
        return unwrap(await api.POST("/api/bars/{barId}/menu/reset", { params: { path }, body: { menuVersion } }));
    }
  }

  async function show(menu: BarMenu) {
    queryClient.setQueryData(ownerQueryKeys.menu(barId), menu);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ownerQueryKeys.menu(barId), refetchType: "all" }),
      queryClient.invalidateQueries({ queryKey: ownerQueryKeys.bar(barId), refetchType: "all" }),
      queryClient.invalidateQueries({ queryKey: ownerQueryKeys.myBars, refetchType: "all" }),
    ]);
  }

  const reloadMenu = () =>
    queryClient.fetchQuery({
      queryKey: ownerQueryKeys.menu(barId),
      queryFn: async ({ signal }) => unwrap(await api.GET("/api/bars/{barId}/menu", { params: { path: { barId } }, signal })),
      staleTime: 0,
    });

  /** Sends `write`; resolves with the menu after it, or throws the failure. Ignored while another is sent. */
  async function send(write: MenuWrite, menuVersion: number | null): Promise<BarMenu | null> {
    if (busy.current) return null;
    busy.current = true;
    setPending(true);
    const key = JSON.stringify(write);
    const resend = unanswered.current?.key === key;
    // The same change again goes with the version it was first sent with.
    const version = resend ? (unanswered.current?.menuVersion ?? null) : menuVersion;
    unanswered.current = null;
    try {
      const menu = await call(write, version);
      await show(menu);
      return menu;
    } catch (failure) {
      if (isRetryable(failure)) unanswered.current = { key, menuVersion: version };
      if (failure instanceof ApiError) {
        if (failure.code === "MENU_OUTDATED" || failure.code === "MENU_ITEM_NOT_FOUND") {
          const fresh = await reloadMenu().catch(() => null);
          if (fresh && resend && failure.code === "MENU_OUTDATED" && appliedIn(fresh, write)) {
            await show(fresh);
            return fresh;
          }
        }
        if (failure.code === "ACTIVE_IMPORT_EXISTS") {
          void queryClient.invalidateQueries({ queryKey: ownerQueryKeys.bar(barId), refetchType: "all" });
        }
      }
      throw failure;
    } finally {
      busy.current = false;
      setPending(false);
    }
  }

  return { send, pending };
}
