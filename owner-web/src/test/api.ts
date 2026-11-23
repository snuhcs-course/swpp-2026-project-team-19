import { http, HttpResponse } from "msw";
import type { BarMenu, MyApplications, MyBars, Me } from "../owner/queries";
import { server } from "./server";

export const ME: Me = {
  userId: "11111111-1111-4111-8111-111111111111",
  email: "owner@example.com",
  displayName: "김사장",
  userType: "customer",
} as Me;

/** A whole bar as GET /api/bars/{barId} and GET /api/me/bars return it (spec 3.6). */
export function bar(barId: string, name: string, extra: Partial<MyBars["items"][number]> = {}): MyBars["items"][number] {
  return {
    barId,
    name,
    address: "서울특별시 관악구 관악로 1",
    latitude: 37.478321,
    longitude: 126.951234,
    phone: null,
    status: "active",
    activeMenuImport: null,
    description: null,
    defaultPourMl: null,
    tags: [],
    weeklyHours: [],
    operatingException: null,
    photos: [],
    currentMenu: null,
    owner: null,
    createdAt: "2026-11-01T03:00:00Z",
    updatedAt: "2026-11-01T03:00:00Z",
    ...extra,
  } as MyBars["items"][number];
}

/** The bar's published menu as GET /api/bars/{barId}/menu returns it (spec 3.9); none by default (3.9.1). */
export function barMenu(source: MyBars["items"][number], extra: Partial<BarMenu> = {}): BarMenu {
  return {
    barId: source.barId,
    name: source.name,
    address: source.address,
    latitude: source.latitude,
    longitude: source.longitude,
    phone: source.phone,
    description: source.description,
    tags: source.tags,
    weeklyHours: source.weeklyHours,
    operatingException: source.operatingException,
    photos: source.photos,
    menuBoardId: null,
    menuVersion: null,
    publishedAt: null,
    items: [],
    ...extra,
  };
}

export function application(status: MyApplications["items"][number]["status"]): MyApplications["items"][number] {
  return { applicationId: crypto.randomUUID(), status } as MyApplications["items"][number];
}

type Application = MyApplications["items"][number];

/** A whole application as the API returns it to its applicant (spec 3.11.1): a pending new_bar by default. */
export function ownerApplication(overrides: Partial<Application> = {}): Application {
  return {
    applicationId: crypto.randomUUID(),
    applicationType: "new_bar",
    status: "pending",
    applicant: { userId: ME.userId, email: ME.email, displayName: ME.displayName },
    bar: null,
    proposedBar: { name: "몰트 앤 무드", address: "서울특별시 관악구 관악로 1 2층", phone: "025551234" },
    businessRegistrationNumber: "1234567891",
    representativeName: "김민준",
    openingDate: "2019-05-14",
    businessStatus: null,
    businessVerification: null,
    warnings: null,
    contactPhone: "01012345678",
    applicantNote: null,
    menuPhotos: [],
    coverPhoto: null,
    rejectionReason: null,
    reviewedAt: null,
    createdAt: "2026-11-20T03:00:00Z",
    updatedAt: "2026-11-20T03:00:00Z",
    ...overrides,
  };
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
    // Spec 3.6: an owned bar, or 403 for a bar the user does not own.
    http.get("/api/bars/:barId", ({ params }) => {
      const found = bars.find((item) => item.barId === params.barId);
      return found ? HttpResponse.json(found) : HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 });
    }),
    // Spec 3.8: no menu imports. Menu import tests serve their own.
    http.get("/api/bars/:barId/menu-imports", () => HttpResponse.json({ items: [], nextCursor: null })),
    // Spec 3.9 is public: any bar answers, here without a menu (3.9.1). Menu tests serve their own.
    http.get("/api/bars/:barId/menu", ({ params }) => {
      const barId = String(params.barId);
      return HttpResponse.json(barMenu(bars.find((item) => item.barId === barId) ?? bar(barId, "매장")));
    }),
  );
}
