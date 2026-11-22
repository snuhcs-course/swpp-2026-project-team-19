import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/errors";
import { imageForm } from "../application/api";
import { clearDraft, loadDraft } from "../application/draft";
import type { PreparedImage } from "../images/prepare";
import { unwrap } from "../api/client";
import type { components, paths } from "../api/schema";
import { useSession } from "../auth/SessionProvider";

type Json<P extends keyof paths, M extends keyof paths[P]> = paths[P][M] extends {
  responses: { 200: { content: { "application/json": infer T } } };
}
  ? T
  : never;

export type Me = Json<"/api/me", "get">;
export type MyBars = Json<"/api/me/bars", "get">;
export type OwnedBar = MyBars["items"][number];
export type MyApplications = Json<"/api/me/owner-applications", "get">;
export type OwnerApplicationDetail = Json<"/api/owner-applications/{applicationId}", "get">;
export type BarDetail = Json<"/api/bars/{barId}", "get">;
export type BarUpdate = components["schemas"]["BarUpdateInput"];

export const ownerQueryKeys = {
  me: ["me"] as const,
  myBars: ["me", "bars"] as const,
  myApplications: ["me", "owner-applications"] as const,
  application: (applicationId: string) => ["owner-applications", applicationId] as const,
  bar: (barId: string) => ["bars", barId] as const,
};

/** The account rarely changes during a visit; screens reuse it instead of asking again on every mount. */
const ME_STALE_MS = 5 * 60 * 1000;

/** GET /api/me: the signed-in user. Called first, since it creates the users row (spec 3.1.4). */
export function useMe() {
  const { api } = useSession();
  return useQuery({
    queryKey: ownerQueryKeys.me,
    queryFn: async ({ signal }) => unwrap(await api.GET("/api/me", { signal })),
    staleTime: ME_STALE_MS,
  });
}

/** GET /api/me/bars: the bars this user owns now (spec 3.11.9). */
export function useMyBars() {
  const { api } = useSession();
  return useQuery({
    queryKey: ownerQueryKeys.myBars,
    queryFn: async ({ signal }) => unwrap(await api.GET("/api/me/bars", { signal })),
  });
}

/** GET /api/me/owner-applications: this user's applications, newest first (spec 3.11.3). */
export function useMyApplications() {
  const { api } = useSession();
  return useQuery({
    queryKey: ownerQueryKeys.myApplications,
    queryFn: async ({ signal }) => unwrap(await api.GET("/api/me/owner-applications", { signal })),
  });
}

/** GET /api/owner-applications/{applicationId}: one of this user's applications (spec 3.11.4). */
export function useOwnerApplication(applicationId: string) {
  const { api } = useSession();
  return useQuery({
    queryKey: ownerQueryKeys.application(applicationId),
    queryFn: async ({ signal }) =>
      unwrap(await api.GET("/api/owner-applications/{applicationId}", { params: { path: { applicationId } }, signal })),
  });
}

/**
 * POST /api/owner-applications/{applicationId}/cancel (spec 3.11.5). Whatever the answer, the list and the
 * application are read again: on success to show it canceled, on 404 the list (it is gone or not this
 * user's), on 409 the application (its status changed meanwhile, e.g. approved, or canceled by a first
 * request whose answer was lost).
 *
 * A draft on this browser for the same application is removed (unless the request failed for another reason,
 * which a retry may fix): its photos can no longer be sent
 * (android/.../data/owner/LiveOwnerScreenRepository.kt `cancelOwnerApplicationLive` drops its staged cover).
 */
export function useCancelApplication() {
  const { api } = useSession();
  const userId = useMe().data?.userId;
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (applicationId: string) =>
      unwrap(await api.POST("/api/owner-applications/{applicationId}/cancel", { params: { path: { applicationId } } })),
    onSuccess: (application) => {
      queryClient.setQueryData(ownerQueryKeys.application(application.applicationId), application);
    },
    onSettled: async (_data, error, applicationId) => {
      // Canceled now, no longer pending (409), or gone (404): no photo can be sent to it any more.
      const code = error instanceof ApiError ? error.code : null;
      const ended = !error || code === "INVALID_APPLICATION_STATE" || code === "OWNER_APPLICATION_NOT_FOUND";
      if (userId && ended && loadDraft(userId)?.applicationId === applicationId) clearDraft(userId);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ownerQueryKeys.myApplications, refetchType: "all" }),
        error ? queryClient.invalidateQueries({ queryKey: ownerQueryKeys.application(applicationId) }) : null,
      ]);
    },
  });
}

/** GET /api/bars/{barId}: the bar and its management state, for its owner's screens (spec 3.6). */
export function useBar(barId: string) {
  const { api } = useSession();
  return useQuery({
    queryKey: ownerQueryKeys.bar(barId),
    queryFn: async ({ signal }) => unwrap(await api.GET("/api/bars/{barId}", { params: { path: { barId } }, signal })),
  });
}

/**
 * PATCH /api/bars/{barId} (spec 3.7). The answer is the bar as the server now has it: it is shown at once,
 * and the bar and the owner's bar list are read again, since both show it.
 */
export function useUpdateBar(barId: string) {
  const { api } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: BarUpdate) =>
      unwrap(await api.PATCH("/api/bars/{barId}", { params: { path: { barId } }, body })),
    onSuccess: async (bar) => {
      queryClient.setQueryData(ownerQueryKeys.bar(barId), bar);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ownerQueryKeys.bar(barId), refetchType: "all" }),
        queryClient.invalidateQueries({ queryKey: ownerQueryKeys.myBars, refetchType: "all" }),
      ]);
    },
  });
}

export type OperatingExceptionInput =
  | components["schemas"]["ClosedTodayInput"]
  | components["schemas"]["CustomHoursInput"]
  | components["schemas"]["VacationInput"];
export type BarPhoto = BarDetail["photos"][number];

/** After a change to the bar: the bar and the owner's bar list are read again, since both show it. */
async function refreshBar(queryClient: ReturnType<typeof useQueryClient>, barId: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ownerQueryKeys.bar(barId), refetchType: "all" }),
    queryClient.invalidateQueries({ queryKey: ownerQueryKeys.myBars, refetchType: "all" }),
  ]);
}

/** PUT /api/bars/{barId}/operating-exception (spec 3.15.2): replaces the bar's temporary closure. */
export function useApplyException(barId: string) {
  const { api } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: OperatingExceptionInput) =>
      unwrap(await api.PUT("/api/bars/{barId}/operating-exception", { params: { path: { barId } }, body })),
    onSuccess: async (bar) => {
      queryClient.setQueryData(ownerQueryKeys.bar(barId), bar);
      await refreshBar(queryClient, barId);
    },
  });
}

/** DELETE /api/bars/{barId}/operating-exception (spec 3.15.3): back to the regular hours; safe to resend. */
export function useCancelException(barId: string) {
  const { api } = useSession();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrap(await api.DELETE("/api/bars/{barId}/operating-exception", { params: { path: { barId } } })),
    onSuccess: async (bar) => {
      queryClient.setQueryData(ownerQueryKeys.bar(barId), bar);
      await refreshBar(queryClient, barId);
    },
  });
}

/**
 * The bar photo calls (spec 3.16.2 to 3.16.4). Each answers the bar's photos in order, shown at once; the
 * bar and the bar list are then read again.
 */
export function useBarPhotoActions(barId: string) {
  const { api } = useSession();
  const queryClient = useQueryClient();
  async function show(photos: BarPhoto[]) {
    queryClient.setQueryData<BarDetail>(ownerQueryKeys.bar(barId), (bar) => (bar ? { ...bar, photos } : bar));
    await refreshBar(queryClient, barId);
    return photos;
  }
  return {
    add: async (image: PreparedImage) =>
      show(
        unwrap(await api.POST("/api/bars/{barId}/photos", { params: { path: { barId } }, body: imageForm("image", [image]) as never }))
          .photos,
      ),
    remove: async (photoId: string) =>
      show(unwrap(await api.DELETE("/api/bars/{barId}/photos/{photoId}", { params: { path: { barId, photoId } } })).photos),
    reorder: async (photoIds: string[]) =>
      show(unwrap(await api.PUT("/api/bars/{barId}/photos/order", { params: { path: { barId } }, body: { photoIds } })).photos),
    /** Shows photos the server sent with an error (409 PHOTOS_OUTDATED `details.photos`). */
    show,
    refresh: () => refreshBar(queryClient, barId),
  };
}
