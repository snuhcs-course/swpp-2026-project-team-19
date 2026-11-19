import { useQuery } from "@tanstack/react-query";
import { unwrap } from "../api/client";
import type { paths } from "../api/schema";
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

export const ownerQueryKeys = {
  me: ["me"] as const,
  myBars: ["me", "bars"] as const,
  myApplications: ["me", "owner-applications"] as const,
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
