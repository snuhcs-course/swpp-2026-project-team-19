import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import type { components } from "../api/schema";
import { unwrap } from "../api/client";
import { useSession } from "../auth/SessionProvider";
import { ownerQueryKeys } from "../owner/queries";
import type { ImportPhoto } from "./photoRules";
import type { ReviewAndApply } from "./review/submit";

export type ImportStatusResponse =
  | components["schemas"]["ImportProcessingResponse"]
  | components["schemas"]["ImportFailedResponse"]
  | components["schemas"]["ImportReviewResponse"]
  | components["schemas"]["ImportAppliedResponse"]
  | components["schemas"]["ImportCanceledResponse"];
export type MenuImportListItem = components["schemas"]["MenuImportListItem"];
export type ImportStatus = components["schemas"]["ImportStatus"];

export const importQueryKeys = {
  menuImport: (menuImportId: string) => ["menu-imports", menuImportId] as const,
  latest: (barId: string) => ["bar-menu-imports", barId, "latest"] as const,
};

/** OwnerMenuPhotoStage7Screen.kt: the import is read again every 2 seconds, 180 times (spec 4.2). */
export const POLL_INTERVAL_MS = 2_000;
export const MAX_POLLS = 180;

export const isActiveStatus = (status: ImportStatus): boolean => status === "uploaded" || status === "processing" || status === "ready_for_review";

/**
 * GET /api/menu-imports/{menuImportId} (spec 5.1): the import's state, and its review once ready (5.4). While it
 * is processing it is read again every 2 seconds until `MAX_POLLS` reads after `firstRead` (the read count when
 * the screen opened or the owner retried).
 */
export function useMenuImport(menuImportId: string, firstRead: number) {
  const { api } = useSession();
  return useQuery({
    queryKey: importQueryKeys.menuImport(menuImportId),
    queryFn: async ({ signal }) =>
      unwrap(await api.GET("/api/menu-imports/{menuImportId}", { params: { path: { menuImportId } }, signal })) as ImportStatusResponse,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      const reads = query.state.dataUpdateCount - firstRead;
      return (status === "uploaded" || status === "processing") && reads < MAX_POLLS ? POLL_INTERVAL_MS : false;
    },
    // A review keeps the owner's input in the screen; reading it again on focus is not needed.
    refetchOnWindowFocus: false,
  });
}

/**
 * GET /api/bars/{barId}/menu-imports?limit=1 (spec 3.8): the bar's latest import, so the menu screen and the home
 * can show an import that failed as the app does (`activeMenuImport` has only unfinished ones).
 */
export function useLatestImport(barId: string) {
  const { api } = useSession();
  return useQuery({
    queryKey: importQueryKeys.latest(barId),
    queryFn: async ({ signal }) =>
      unwrap(await api.GET("/api/bars/{barId}/menu-imports", { params: { path: { barId }, query: { limit: 1 } }, signal })).items[0] ?? null,
  });
}

/** The import requests of the review and status screens, and what each one reads again afterwards. */
export function useImportActions(barId: string) {
  const { api } = useSession();
  const queryClient = useQueryClient();

  /** After an import starts, ends or is applied: the bar (its `activeMenuImport`), the bar list, the latest import. */
  const refreshBar = useCallback(
    () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ownerQueryKeys.bar(barId), refetchType: "all" }),
        queryClient.invalidateQueries({ queryKey: ownerQueryKeys.myBars, refetchType: "all" }),
        queryClient.invalidateQueries({ queryKey: importQueryKeys.latest(barId), refetchType: "all" }),
      ]),
    [barId, queryClient],
  );

  // The same functions on every render, so screens can depend on them (the review's draft queue does).
  return useMemo(() => ({
    refreshBar,

    /** After a publish, answered or confirmed later: the bar, the bar list, the latest import and the menu (3.9). */
    refreshApplied: () =>
      Promise.all([refreshBar(), queryClient.invalidateQueries({ queryKey: ownerQueryKeys.menu(barId), refetchType: "all" })]),

    /** POST /api/bars/{barId}/menu-imports (spec 4.1): the photos in order, as a partial update (the app's only mode). */
    upload: async (photos: readonly ImportPhoto[], idempotencyKey: string) => {
      const form = new FormData();
      form.append("mode", "partial_update");
      for (const photo of photos) form.append("images", new File([photo.file], photo.file.name || "menu-photo", { type: photo.type }));
      const accepted = unwrap(
        await api.POST("/api/bars/{barId}/menu-imports", {
          params: { path: { barId }, header: { "Idempotency-Key": idempotencyKey } },
          body: form as never,
        }),
      );
      await refreshBar();
      return accepted;
    },

    /** POST /api/menu-imports/{menuImportId}/cancel (spec 5.7); canceling again answers the same. */
    cancel: async (menuImportId: string) => {
      const canceled = unwrap(await api.POST("/api/menu-imports/{menuImportId}/cancel", { params: { path: { menuImportId } } }));
      queryClient.setQueryData(importQueryKeys.menuImport(menuImportId), canceled);
      await refreshBar();
      return canceled;
    },

    /** PUT /api/menu-imports/{menuImportId}/review-draft (spec 5.9). */
    saveDraft: async (menuImportId: string, body: components["schemas"]["ReviewDraftRequest"]) =>
      unwrap(await api.PUT("/api/menu-imports/{menuImportId}/review-draft", { params: { path: { menuImportId } }, body })),

    /** POST /api/menu-imports/{menuImportId}/review-and-apply (spec 8); then the menu, the bar and the import are read again. */
    apply: async (menuImportId: string, body: ReviewAndApply) => {
      const applied = unwrap(await api.POST("/api/menu-imports/{menuImportId}/review-and-apply", { params: { path: { menuImportId } }, body }));
      await Promise.all([refreshBar(), queryClient.invalidateQueries({ queryKey: ownerQueryKeys.menu(barId), refetchType: "all" })]);
      return applied;
    },

    /** The import as the server has it now, past the cache (an unknown answer, an expired photo URL). */
    readNow: (menuImportId: string) =>
      queryClient.fetchQuery({
        queryKey: importQueryKeys.menuImport(menuImportId),
        queryFn: async () =>
          unwrap(await api.GET("/api/menu-imports/{menuImportId}", { params: { path: { menuImportId } } })) as ImportStatusResponse,
        staleTime: 0,
      }),

    /**
     * The import as the server has it now, without replacing the screen's copy: after an unknown publish answer
     * the review shows its own result instead of the status screen.
     */
    peek: async (menuImportId: string) =>
      unwrap(await api.GET("/api/menu-imports/{menuImportId}", { params: { path: { menuImportId } } })) as ImportStatusResponse,

    /** GET /api/catalog/products (spec 7), inactive products too. */
    searchCatalog: async (query: string) => unwrap(await api.GET("/api/catalog/products", { params: { query: { query } } })).items,
  }), [api, barId, queryClient, refreshBar]);
}
