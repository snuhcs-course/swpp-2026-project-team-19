import { http, HttpResponse } from "msw";
import type { MyApplications, MyBars, Me } from "../owner/queries";
import { server } from "./server";

export const ME: Me = {
  userId: "11111111-1111-4111-8111-111111111111",
  email: "owner@example.com",
  displayName: "김사장",
  userType: "customer",
} as Me;

export function bar(barId: string, name: string): MyBars["items"][number] {
  return { barId, name } as MyBars["items"][number];
}

export function application(status: MyApplications["items"][number]["status"]): MyApplications["items"][number] {
  return { applicationId: crypto.randomUUID(), status } as MyApplications["items"][number];
}

export function errorBody(code: string, message = "오류") {
  return { error: { code, message, details: null, fieldErrors: [] } };
}

/** The owner's account, bars and applications as the API returns them. */
export function useOwnerApi({ bars = [], applications = [] }: { bars?: MyBars["items"]; applications?: MyApplications["items"] } = {}) {
  server.use(
    http.get("/api/me", () => HttpResponse.json(ME)),
    http.get("/api/me/bars", () => HttpResponse.json({ items: bars })),
    http.get("/api/me/owner-applications", () => HttpResponse.json({ items: applications })),
  );
}
