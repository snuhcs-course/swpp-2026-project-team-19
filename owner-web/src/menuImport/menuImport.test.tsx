import { act, configure, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { components } from "../api/schema";
import type { BarMenu, CatalogProduct } from "../owner/queries";
import { bar, barMenu, errorBody, ME, useOwnerApi } from "../test/api";
import { candidate, line, lineOption, menuItem, otherLine, savedOption, unmatchedLine } from "../test/menuImport";
import { renderOwnerWeb } from "../test/render";
import { server } from "../test/server";
import type { ImportReview, ReviewLine } from "./review/mapping";
import { normalizedUnlinkedMenuName } from "./review/rules";

// Drafts are saved a second after a change (useDraftSync.ts), so waits here allow more than the default second.
configure({ asyncUtilTimeout: 3000 });

const BAR_ID = "22222222-2222-4222-8222-222222222222";
const IMPORT_ID = "77777777-7777-4777-8777-777777777777";
const P12 = "44444444-4444-4444-8444-444444444412";
const P16 = "44444444-4444-4444-8444-444444444416";
const user = () => userEvent.setup();
const title = (name: string | RegExp) => screen.findByRole("heading", { level: 1, name });
const MENU_PATH = `/bars/${BAR_ID}/menu`;
const JOB_PATH = `/bars/${BAR_ID}/menu/import/${IMPORT_ID}`;

type ImportStatus = components["schemas"]["ImportStatus"];
type Call = { method: string; path: string; body: unknown; key?: string | null };
type Answer = (call: Call) => Response | undefined | Promise<Response | undefined>;
type Job = {
  status: ImportStatus;
  progress: { totalImages: number; completedImages: number; failedImages: number };
  failure: { code: "IMAGE_EXTRACTION_FAILED" | "PROCESSING_FAILED"; message: string } | null;
  reviewVersion: number;
  /** The states the next reads move through, one per read. */
  next: ImportStatus[];
  imageUrl: string;
  imageUrlExpiresAt: string | null;
  lines: ReviewLine[];
  draft: { draftVersion: number; reviewVersion: number; savedAt: string; content: Record<string, unknown> } | null;
  draftVersion: number;
  key: string | null;
  fingerprint: string;
};

const DISCOUNT = { discountedPriceKrw: 29000, startsAt: "2000-01-01T00:00:00Z", endsAt: "2999-01-01T00:00:00Z" };

/** The bar's menu before the import: a linked whisky with a discounted 60ml, a sold-out other menu, a whisky not on the photos. */
const startingMenu = () => [
  menuItem({ barMenuItemId: "gf", productId: P12, productName: "Glenfiddich 12", category: "whisky", displayName: "Glenfiddich 12", sortOrder: 1, options: [savedOption("gf-30", null, 30, 17000), savedOption("gf-60", null, 60, 32000, DISCOUNT)] }),
  menuItem({ barMenuItemId: "hb", kind: "other", displayName: "하우스 하이볼", sortOrder: 2, soldOut: true, options: [savedOption("hb-1", null, null, 9000)] }),
  menuItem({ barMenuItemId: "lg", productId: P16, productName: "Lagavulin 16", category: "whisky", displayName: "Lagavulin 16", sortOrder: 3, options: [savedOption("lg-30", null, 30, 25000)] }),
];

/** The photo's lines: Glenfiddich 12 at a new 30ml price, a whisky the catalog lacks, another menu and a header. */
const photoLines = (): ReviewLine[] => [
  line({ extractedItemId: "l-head", itemOrder: 1, rawText: "WHISKY", effectiveLineType: "section_header", extractedLineType: "section_header", extractedKind: null, initialResolutionStatus: null, extractedProductName: null, proposedProductId: null, options: [], candidates: [], newProductDraft: null }),
  line({ extractedItemId: "l-gf", itemOrder: 2, rawText: "글렌피딕 12년 30ml 18,000", extractedProductName: "글렌피딕 12년", proposedProductId: P12, candidates: [candidate(P12, "Glenfiddich 12")], options: [lineOption("o-gf-30", null, 30, 18000)] }),
  unmatchedLine({ extractedItemId: "l-new", itemOrder: 3, rawText: "새 위스키 21년 30ml 40,000", extractedProductName: "새 위스키 21년", newProductDraft: null, options: [lineOption("o-new-30", null, 30, 40000)] }),
  otherLine({ extractedItemId: "l-sour", itemOrder: 4, rawText: "레몬 사워 12,000", extractedProductName: "레몬 사워", options: [lineOption("o-sour", null, null, 12000)] }),
];

/**
 * The menu import API as the backend keeps it (spec 4, 5, 8): one unfinished import per bar, the same key and
 * photos answering the same import, drafts versioned, and a partial update that keeps the items it does not
 * name, the sold-out mark of the items it updates, and a discount where an option stays the same. `answer`
 * may answer a call first.
 */
function importServer({
  items = startingMenu(),
  job: initial = null,
  latest = null,
  answer,
  products = [],
  defaultPourMl = 30,
}: {
  items?: BarMenu["items"];
  job?: Partial<Job> | null;
  latest?: { status: ImportStatus } | null;
  answer?: Answer;
  products?: CatalogProduct[];
  defaultPourMl?: number | null;
} = {}) {
  const fresh = (extra: Partial<Job>): Job => ({
    status: "processing",
    progress: { totalImages: 2, completedImages: 0, failedImages: 0 },
    failure: null,
    reviewVersion: 1,
    next: [],
    imageUrl: "https://signed.example/photo-1?v=1",
    imageUrlExpiresAt: null,
    lines: photoLines(),
    draft: null,
    draftVersion: 0,
    key: null,
    fingerprint: "",
    ...extra,
  });
  let job: Job | null = initial ? fresh(initial) : null;
  let pour = defaultPourMl;
  const owned = () => bar(BAR_ID, "관악 위스키 바", { defaultPourMl: pour, activeMenuImport: job && ["uploaded", "processing", "ready_for_review"].includes(job.status) ? { menuImportId: IMPORT_ID, status: job.status as "processing" } : null });
  let menu: BarMenu = barMenu(owned(), { menuBoardId: "board", menuVersion: 4, publishedAt: "2026-11-01T03:00:00Z", items });
  const calls: Call[] = [];
  const reads = { job: 0 };
  let added = 0;
  useOwnerApi({ bars: [owned()] });
  const record = async (call: Call) => {
    calls.push(call);
    return answer?.(call);
  };
  const review = (): ImportReview => ({
    menuImportId: IMPORT_ID,
    barId: BAR_ID,
    mode: "partial_update",
    status: "ready_for_review",
    reviewVersion: job!.reviewVersion,
    images: [{ imageId: "img-1", imageOrder: 1, imageUrl: job!.imageUrl, imageUrlExpiresAt: job!.imageUrlExpiresAt, items: job!.lines }],
    reviewDraft: job!.draft,
    proposedChanges: [
      { changeId: "c-gf", changeType: "update", barMenuItemId: "gf", extractedItemId: "l-gf", extractedItemIds: ["l-gf"], before: null, after: null, summary: "", decision: "pending" },
      { changeId: "c-new", changeType: "add", barMenuItemId: null, extractedItemId: "l-new", extractedItemIds: ["l-new"], before: null, after: null, summary: "", decision: "pending" },
      { changeId: "c-sour", changeType: "add", barMenuItemId: null, extractedItemId: "l-sour", extractedItemIds: ["l-sour"], before: null, after: null, summary: "", decision: "pending" },
    ],
  });
  const statusBody = () => {
    const j = job!;
    switch (j.status) {
      case "uploaded":
      case "processing":
        return { menuImportId: IMPORT_ID, status: j.status, progress: j.progress, pollAfterMs: 3000 };
      case "failed":
        return { menuImportId: IMPORT_ID, status: "failed", progress: j.progress, failure: j.failure };
      case "ready_for_review":
        return review();
      case "applied":
        return { menuImportId: IMPORT_ID, barId: BAR_ID, status: "applied", reviewVersion: j.reviewVersion, appliedAt: "2026-11-23T03:00:00Z", menuBoardId: "board" };
      case "canceled":
        return { menuImportId: IMPORT_ID, barId: BAR_ID, status: "canceled", canceledAt: "2026-11-23T03:00:00Z" };
    }
  };
  const conflict = (code: string, details: Record<string, unknown>) => HttpResponse.json({ error: { code, message: code, details, fieldErrors: [] } }, { status: 409 });

  server.use(
    http.get("/api/me/bars", () => HttpResponse.json({ items: [owned()] })),
    http.get("/api/bars/:barId", () => HttpResponse.json(owned())),
    http.patch("/api/bars/:barId", async ({ request }) => {
      const body = (await request.json()) as { defaultPourMl: number };
      const custom = await record({ method: "PATCH", path: `/api/bars/${BAR_ID}`, body });
      if (custom) return custom;
      pour = body.defaultPourMl;
      return HttpResponse.json(owned());
    }),
    http.get("/api/bars/:barId/menu", () => HttpResponse.json(menu)),
    http.get("/api/bars/:barId/menu-imports", () =>
      HttpResponse.json({
        items: job ? [{ menuImportId: IMPORT_ID, mode: "partial_update", status: job.status, imageCount: 2, reviewVersion: job.reviewVersion, ownerNote: null, createdAt: "2026-11-23T00:00:00Z", completedAt: null }] : latest ? [{ menuImportId: IMPORT_ID, mode: "partial_update", status: latest.status, imageCount: 2, reviewVersion: 1, ownerNote: null, createdAt: "2026-11-20T00:00:00Z", completedAt: null }] : [],
        nextCursor: null,
      }),
    ),
    http.get("/api/catalog/products", async ({ request }) => {
      const query = new URL(request.url).searchParams.get("query") ?? "";
      const custom = await record({ method: "GET", path: `/api/catalog/products?query=${query}`, body: null });
      return custom ?? HttpResponse.json({ items: products });
    }),
    http.post("/api/bars/:barId/menu-imports", async ({ request }) => {
      const form = await request.formData();
      const files = form.getAll("images") as File[];
      const key = request.headers.get("Idempotency-Key");
      const body = { mode: form.get("mode"), images: files.map((file) => ({ name: file.name, type: file.type, size: file.size })) };
      const custom = await record({ method: "POST", path: `/api/bars/${BAR_ID}/menu-imports`, body, key });
      if (custom) return custom;
      const fingerprint = JSON.stringify(body);
      // Spec 4.3: the same key and photos answer the same import; another key while one is unfinished is refused.
      if (job && job.key === key && job.fingerprint === fingerprint) {
        return HttpResponse.json({ menuImportId: IMPORT_ID, status: job.status, imageCount: files.length, statusUrl: `/api/menu-imports/${IMPORT_ID}`, pollAfterMs: 3000 }, { status: 202 });
      }
      if (job && ["uploaded", "processing", "ready_for_review"].includes(job.status)) return conflict("ACTIVE_IMPORT_EXISTS", { menuImportId: IMPORT_ID, status: job.status });
      job = fresh({ key, fingerprint, progress: { totalImages: files.length, completedImages: 0, failedImages: 0 } });
      return HttpResponse.json({ menuImportId: IMPORT_ID, status: "processing", imageCount: files.length, statusUrl: `/api/menu-imports/${IMPORT_ID}`, pollAfterMs: 3000 }, { status: 202 });
    }),
    http.get("/api/menu-imports/:menuImportId", async ({ params }) => {
      const custom = await record({ method: "GET", path: `/api/menu-imports/${String(params.menuImportId)}`, body: null });
      if (custom) return custom;
      if (!job || params.menuImportId !== IMPORT_ID) return HttpResponse.json(errorBody("MENU_IMPORT_NOT_FOUND"), { status: 404 });
      reads.job++;
      const next = job.next.shift();
      if (next) {
        job.status = next;
        if (next === "processing") job.progress = { ...job.progress, completedImages: Math.min(job.progress.totalImages, job.progress.completedImages + 1) };
      }
      return HttpResponse.json(statusBody());
    }),
    http.post("/api/menu-imports/:menuImportId/cancel", async () => {
      const custom = await record({ method: "POST", path: `/api/menu-imports/${IMPORT_ID}/cancel`, body: null });
      if (custom) return custom;
      if (job && (job.status === "applied" || job.status === "failed")) return conflict("INVALID_IMPORT_STATE", { menuImportId: IMPORT_ID, status: job.status });
      job!.status = "canceled";
      job!.draft = null;
      return HttpResponse.json(statusBody());
    }),
    http.put("/api/menu-imports/:menuImportId/review-draft", async ({ request }) => {
      const body = (await request.json()) as { draftVersion: number; reviewVersion: number; content: Record<string, unknown> };
      const custom = await record({ method: "PUT", path: `/api/menu-imports/${IMPORT_ID}/review-draft`, body });
      if (custom) return custom;
      if (job!.status !== "ready_for_review") return conflict("INVALID_IMPORT_STATE", { menuImportId: IMPORT_ID, status: job!.status });
      if (body.draftVersion !== job!.draftVersion) {
        return conflict("REVIEW_DRAFT_OUTDATED", { currentDraftVersion: job!.draftVersion, savedAt: "2026-11-23T01:00:00Z", reviewUrl: `/api/menu-imports/${IMPORT_ID}` });
      }
      job!.draftVersion += 1;
      job!.draft = { draftVersion: job!.draftVersion, reviewVersion: body.reviewVersion, savedAt: "2026-11-23T01:00:00Z", content: body.content };
      return HttpResponse.json({ menuImportId: IMPORT_ID, draftVersion: job!.draftVersion, savedAt: "2026-11-23T01:00:00Z" });
    }),
    http.post("/api/menu-imports/:menuImportId/review-and-apply", async ({ request }) => {
      const body = (await request.json()) as { reviewVersion: number; itemDecisions: Record<string, unknown>[]; changeDecisions: unknown[] };
      const custom = await record({ method: "POST", path: `/api/menu-imports/${IMPORT_ID}/review-and-apply`, body });
      if (custom) return custom;
      if (job!.status !== "ready_for_review") return conflict("INVALID_IMPORT_STATE", { menuImportId: IMPORT_ID, status: job!.status });
      let result = { added: 0, updated: 0, removed: 0, ignored: 0, createdBrands: 0, createdProducts: 0, unlinkedWhisky: 0 };
      let next = [...menu.items];
      for (const decision of body.itemDecisions) {
        if (decision.action !== "select_existing_product" && decision.action !== "publish_without_product") continue;
        const linked = decision.action === "select_existing_product" ? (decision.productId as string) : null;
        const name = (decision.correctedProductName as string | null) ?? job!.lines.find((l) => l.extractedItemId === decision.extractedItemId)?.extractedProductName ?? "";
        const existing = next.find((item) => (linked ? item.productId === linked : item.productId === null && normalizedUnlinkedMenuName(item.displayName) === normalizedUnlinkedMenuName(name)));
        const options = (decision.options as { optionLabel: string | null; pourMl: number | null; priceKrw: number }[]).map((option, index) => {
          // Spec 8.7: a discount stays on an option whose label, pour and price are unchanged.
          const same = existing?.options.find((old) => old.optionLabel === option.optionLabel && old.pourMl === option.pourMl && old.priceKrw === option.priceKrw);
          return savedOption(`new-${decision.extractedItemId as string}-${index}`, option.optionLabel, option.pourMl, option.priceKrw, same?.discount ?? null);
        });
        if (existing) {
          next = next.map((item) => (item === existing ? { ...item, options } : item));
          result = { ...result, updated: result.updated + 1 };
        } else {
          added++;
          next.push(menuItem({ barMenuItemId: `added-${added}`, productId: linked, kind: decision.kind === "other" ? "other" : "whisky", displayName: name, sortOrder: next.length + 1, options }));
          result = { ...result, added: result.added + 1, unlinkedWhisky: result.unlinkedWhisky + (decision.kind === "whisky" ? 1 : 0) };
        }
      }
      menu = { ...menu, menuVersion: (menu.menuVersion ?? 0) + 1, items: next };
      job!.status = "applied";
      job!.draft = null;
      return HttpResponse.json({ menuImportId: IMPORT_ID, status: "applied", reviewVersion: body.reviewVersion, appliedAt: "2026-11-23T03:00:00Z", menuBoardId: "board", result });
    }),
  );
  return {
    calls,
    reads,
    callsTo: (method: string, path: string) => calls.filter((call) => call.method === method && call.path.startsWith(path)),
    get menu() {
      return menu;
    },
    get job() {
      return job;
    },
    setJob: (update: Partial<Job>) => {
      job = job ? { ...job, ...update } : fresh(update);
    },
  };
}

/** A photo file of `size` bytes with JPEG or PNG bytes at its start. */
function photoFile(name: string, kind: "jpeg" | "png" | "webp" = "jpeg", size = 64): File {
  const head = kind === "jpeg" ? [0xff, 0xd8, 0xff, 0xe0] : kind === "png" ? [137, 80, 78, 71, 13, 10, 26, 10] : [0x52, 0x49, 0x46, 0x46];
  const bytes = new Uint8Array(size);
  bytes.set(head);
  return new File([bytes], name, { type: `image/${kind}` });
}

const pickPhotos = async (files: File[]) => fireEvent.change(await screen.findByLabelText(/사진 추가/), { target: { files } });
const deferred = () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => (release = resolve));
  return { gate, release };
};
const networkFailure = () => HttpResponse.error();

beforeEach(() => {
  URL.createObjectURL = vi.fn((file: Blob) => `blob:${(file as File).name}`);
  URL.revokeObjectURL = vi.fn();
  localStorage.clear();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("uploading menu photos (spec 4, OwnerMenuPhotoSelectionScreen.kt)", () => {
  it("sends the photos in the order on screen, as a partial update with a new key, and opens the import", async () => {
    const api = importServer({ job: null });
    renderOwnerWeb(`/bars/${BAR_ID}/menu/import`);
    await title("메뉴판 사진 선택");
    await pickPhotos([photoFile("page-1.jpg", "jpeg", 61), photoFile("page-2.png", "png", 62), photoFile("page-3.jpg", "jpeg", 63)]);
    await screen.findByRole("listitem", { name: "메뉴판 사진 3" });
    await user().click(screen.getByRole("button", { name: "사진 3 앞으로" }));
    await user().click(screen.getByRole("button", { name: "사진 1 빼기" }));
    expect(screen.getByText("2/15")).toBeInTheDocument();
    await user().click(screen.getByRole("button", { name: "사진 2장 올리기" }));

    await screen.findByText("사진 2장 중 0장을 읽었어요");
    const [upload] = api.callsTo("POST", `/api/bars/${BAR_ID}/menu-imports`);
    // The order sent is the order on screen (4.1 imageOrder); jsdom names every file "blob", so sizes tell them apart.
    expect(upload!.body).toMatchObject({
      mode: "partial_update",
      images: [
        { type: "image/jpeg", size: 63 },
        { type: "image/png", size: 62 },
      ],
    });
    expect(upload!.key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("checks the photos before sending: JPEG or PNG only, 10 MB each, 15 at most", async () => {
    const api = importServer({ job: null });
    renderOwnerWeb(`/bars/${BAR_ID}/menu/import`);
    await title("메뉴판 사진 선택");
    await pickPhotos([photoFile("ok.jpg"), photoFile("menu.webp", "webp")]);
    expect(await screen.findByRole("alert")).toHaveTextContent("JPEG 또는 PNG 사진만 올릴 수 있어요.");
    const big = photoFile("big.jpg");
    Object.defineProperty(big, "size", { value: 10 * 1024 * 1024 + 1 });
    await pickPhotos([big]);
    expect(await screen.findByRole("alert")).toHaveTextContent("사진 한 장은 최대 10MB까지 가능해요.");
    await pickPhotos(Array.from({ length: 16 }, (_, i) => photoFile(`p${i}.jpg`)));
    expect(await screen.findByRole("alert")).toHaveTextContent("사진은 최대 15장까지 선택할 수 있어요.");
    expect(screen.getByRole("button", { name: "사진 0장 올리기" })).toBeDisabled();
    expect(api.callsTo("POST", `/api/bars/${BAR_ID}/menu-imports`)).toHaveLength(0);
  });

  it("sends the same photos again with the same key after a lost answer, and new photos with a new key", async () => {
    let lose = 1;
    const api = importServer({ job: null, answer: (call) => (call.method === "POST" && call.path.endsWith("/menu-imports") && lose-- > 0 ? networkFailure() : undefined) });
    renderOwnerWeb(`/bars/${BAR_ID}/menu/import`);
    await title("메뉴판 사진 선택");
    await pickPhotos([photoFile("a.jpg")]);
    await user().click(await screen.findByRole("button", { name: "사진 1장 올리기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("인터넷 연결을 확인해 주세요.");
    await user().click(screen.getByRole("button", { name: "사진 1장 올리기" }));
    await screen.findByText("사진 1장 중 0장을 읽었어요");
    const [lost, again] = api.callsTo("POST", `/api/bars/${BAR_ID}/menu-imports`);
    expect(again!.key).toBe(lost!.key);
  });

  it("uses a new key once the photos change after a failure", async () => {
    let lose = 1;
    const api = importServer({ job: null, answer: (call) => (call.method === "POST" && call.path.endsWith("/menu-imports") && lose-- > 0 ? networkFailure() : undefined) });
    renderOwnerWeb(`/bars/${BAR_ID}/menu/import`);
    await title("메뉴판 사진 선택");
    await pickPhotos([photoFile("a.jpg")]);
    await user().click(await screen.findByRole("button", { name: "사진 1장 올리기" }));
    await screen.findByRole("alert");
    await pickPhotos([photoFile("b.jpg")]);
    await user().click(await screen.findByRole("button", { name: "사진 2장 올리기" }));
    await screen.findByText("사진 2장 중 0장을 읽었어요");
    const [first, second] = api.callsTo("POST", `/api/bars/${BAR_ID}/menu-imports`);
    expect(second!.key).not.toBe(first!.key);
  });

  it("opens the unfinished import another device started instead (409 ACTIVE_IMPORT_EXISTS)", async () => {
    const api = importServer({ job: null });
    renderOwnerWeb(`/bars/${BAR_ID}/menu/import`);
    await title("메뉴판 사진 선택");
    api.setJob({ status: "processing" });
    await pickPhotos([photoFile("a.jpg")]);
    await user().click(await screen.findByRole("button", { name: "사진 1장 올리기" }));
    expect(await screen.findByText("진행 중인 메뉴판 작업이 있어 그 작업으로 이동했어요.")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: "메뉴판 분석 중" })).toBeInTheDocument();
  });

  it.each([
    ["UPLOAD_TOO_LARGE", 413, null, "사진이 너무 많거나 커요. 사진 수를 줄이거나 더 작은 사진으로 바꿔 주세요."],
    ["UNSUPPORTED_IMAGE_TYPE", 415, { imageOrder: 1 }, "1번째 사진은 올릴 수 없는 형식이에요. JPEG나 PNG 사진으로 바꿔 주세요."],
    ["VALIDATION_FAILED", 422, null, "입력값을 확인해 주세요."],
    ["INTERNAL_ERROR", 500, null, "서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요."],
    ["FORBIDDEN", 403, null, "이 매장을 관리할 권한이 없어요."],
  ])("shows %s from the upload and keeps the photos", async (code, status, details, message) => {
    importServer({
      job: null,
      answer: (call) =>
        call.method === "POST" && call.path.endsWith("/menu-imports")
          ? HttpResponse.json({ error: { code, message: "입력값을 확인해 주세요.", details, fieldErrors: [] } }, { status })
          : undefined,
    });
    renderOwnerWeb(`/bars/${BAR_ID}/menu/import`);
    await title("메뉴판 사진 선택");
    await pickPhotos([photoFile("a.jpg")]);
    await user().click(await screen.findByRole("button", { name: "사진 1장 올리기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByRole("listitem", { name: "메뉴판 사진 1" })).toBeInTheDocument();
  });

  it("sends a new key after the server said the key was used for other photos (409 IDEMPOTENCY_KEY_REUSED)", async () => {
    let reused = 1;
    const api = importServer({ job: null, answer: (call) => (call.method === "POST" && call.path.endsWith("/menu-imports") && reused-- > 0 ? HttpResponse.json(errorBody("IDEMPOTENCY_KEY_REUSED"), { status: 409 }) : undefined) });
    renderOwnerWeb(`/bars/${BAR_ID}/menu/import`);
    await title("메뉴판 사진 선택");
    await pickPhotos([photoFile("a.jpg")]);
    await user().click(await screen.findByRole("button", { name: "사진 1장 올리기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("요청이 겹쳤어요. 다시 올려 주세요.");
    await user().click(screen.getByRole("button", { name: "사진 1장 올리기" }));
    await screen.findByText("사진 1장 중 0장을 읽었어요");
    const [refused, again] = api.callsTo("POST", `/api/bars/${BAR_ID}/menu-imports`);
    expect(again!.key).not.toBe(refused!.key);
  });

  it("locks the screen while a slow upload runs and sends it once", async () => {
    const slow = deferred();
    const api = importServer({ job: null, answer: async (call) => (call.method === "POST" && call.path.endsWith("/menu-imports") ? (await slow.gate, undefined) : undefined) });
    renderOwnerWeb(`/bars/${BAR_ID}/menu/import`);
    await title("메뉴판 사진 선택");
    await pickPhotos([photoFile("a.jpg")]);
    await user().click(await screen.findByRole("button", { name: "사진 1장 올리기" }));
    expect(await screen.findByRole("button", { name: /사진을 올리고 있어요/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "사진 1 빼기" })).toBeDisabled();
    slow.release();
    await screen.findByText("사진 1장 중 0장을 읽었어요");
    expect(api.callsTo("POST", `/api/bars/${BAR_ID}/menu-imports`)).toHaveLength(1);
  });

  it("points to the unfinished import instead of a new upload", async () => {
    importServer({ job: { status: "ready_for_review" } });
    renderOwnerWeb(`/bars/${BAR_ID}/menu/import`);
    expect(await screen.findByText("진행 중인 메뉴판 작업이 있어요. 먼저 기존 작업을 확인해 주세요.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "기존 작업 확인" })).toHaveAttribute("href", `/owner${JOB_PATH}`);
  });
});

describe("the import's state (spec 5, OwnerMenuPhotoJobScreen.kt)", () => {
  it("reads a processing import every 2 seconds until its review is ready", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const api = importServer({ job: { status: "processing", next: ["processing", "processing", "ready_for_review"] } });
    renderOwnerWeb(JOB_PATH);
    expect(await screen.findByText("사진 2장 중 1장을 읽었어요")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(await screen.findByText("사진 2장 중 2장을 읽었어요")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(await title("메뉴 검수")).toBeInTheDocument();
    const reads = api.reads.job;
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(api.reads.job).toBe(reads);
  });

  it("stops after 180 reads and says the analysis is taking long", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const api = importServer({ job: { status: "processing" } });
    renderOwnerWeb(JOB_PATH);
    await screen.findByText("사진 2장 중 0장을 읽었어요");
    for (let i = 0; i < 180; i++) await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(await screen.findByText("분석 시간이 길어지고 있어요. 나갔다가 다시 확인해 주세요.")).toBeInTheDocument();
    const reads = api.reads.job;
    await act(() => vi.advanceTimersByTimeAsync(20_000));
    expect(api.reads.job).toBe(reads);
    expect(reads).toBe(180);
  });

  it("shows the server's failure message and offers a new upload (5.3)", async () => {
    importServer({ job: { status: "failed", progress: { totalImages: 2, completedImages: 1, failedImages: 1 }, failure: { code: "IMAGE_EXTRACTION_FAILED", message: "일부 메뉴 이미지를 처리하지 못했습니다." } } });
    renderOwnerWeb(JOB_PATH);
    expect(await screen.findByRole("alert")).toHaveTextContent("일부 메뉴 이미지를 처리하지 못했습니다.");
    expect(screen.getByText(/사진 2장 중 1장을 읽었어요/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "사진 다시 올리기" })).toHaveAttribute("href", `/owner/bars/${BAR_ID}/menu/import`);
  });

  it("says a canceled import is over and a new one can start (5.6)", async () => {
    importServer({ job: { status: "canceled" } });
    renderOwnerWeb(JOB_PATH);
    expect(await screen.findByRole("heading", { level: 2, name: "작업이 취소됐어요" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "새 메뉴판 사진 올리기" })).toBeInTheDocument();
  });

  it("says an applied import was published (5.5)", async () => {
    importServer({ job: { status: "applied" } });
    renderOwnerWeb(JOB_PATH);
    expect(await screen.findByRole("heading", { level: 2, name: "이미 게시된 작업이에요" })).toBeInTheDocument();
  });

  it("says an import that does not exist cannot be found (404 MENU_IMPORT_NOT_FOUND)", async () => {
    importServer({ job: null });
    renderOwnerWeb(JOB_PATH);
    expect(await screen.findByText("메뉴판 작업을 찾을 수 없어요.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "메뉴 관리로" })).toBeInTheDocument();
  });

  it("offers no retry for 403 and retries a failed read", async () => {
    let fail: "forbidden" | "server" | null = "forbidden";
    importServer({
      job: { status: "processing" },
      answer: (call) =>
        call.method === "GET" && call.path.startsWith("/api/menu-imports/") && fail
          ? HttpResponse.json(errorBody(fail === "forbidden" ? "FORBIDDEN" : "INTERNAL_ERROR"), { status: fail === "forbidden" ? 403 : 500 })
          : undefined,
    });
    const first = renderOwnerWeb(JOB_PATH);
    expect(await screen.findByText("이 화면을 볼 권한이 없어요.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    first.unmount();
    fail = "server";
    renderOwnerWeb(JOB_PATH);
    await user().click(await screen.findByRole("button", { name: "다시 시도" }));
    fail = null;
    await user().click(await screen.findByRole("button", { name: "다시 시도" }));
    expect(await screen.findByText("사진 2장 중 0장을 읽었어요")).toBeInTheDocument();
  });

  it("offers no retry when a later read is forbidden, keeping the last state (Codex review on #210)", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    let forbidden = false;
    importServer({
      job: { status: "processing" },
      answer: (call) => (call.method === "GET" && call.path.startsWith("/api/menu-imports/") && forbidden ? HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 }) : undefined),
    });
    renderOwnerWeb(JOB_PATH);
    await screen.findByText("사진 2장 중 0장을 읽었어요");
    forbidden = true;
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(await screen.findByRole("alert")).toHaveTextContent("최신 정보를 불러오지 못했어요. 이 화면을 볼 권한이 없어요.");
    expect(screen.getByText("사진 2장 중 0장을 읽었어요")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
  });

  it("offers one retry when a later read fails, keeping the last state", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    let failing = false;
    importServer({
      job: { status: "processing", next: ["processing", "processing"] },
      answer: (call) => (call.method === "GET" && call.path.startsWith("/api/menu-imports/") && failing ? HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 }) : undefined),
    });
    renderOwnerWeb(JOB_PATH);
    await screen.findByText("사진 2장 중 1장을 읽었어요");
    failing = true;
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(await screen.findByRole("alert")).toHaveTextContent("최신 정보를 불러오지 못했어요.");
    expect(screen.getAllByRole("button", { name: "다시 시도" })).toHaveLength(1);
    failing = false;
    await user().click(screen.getByRole("button", { name: "다시 시도" }));
    expect(await screen.findByText("사진 2장 중 2장을 읽었어요")).toBeInTheDocument();
  });

  it("shows the same screen when the import's page is opened again (another tab, a reload)", async () => {
    importServer({ job: { status: "ready_for_review" } });
    const first = renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    first.unmount();
    renderOwnerWeb(JOB_PATH);
    expect(await title("메뉴 검수")).toBeInTheDocument();
    expect(await screen.findByText(/검수 \d+\/\d+ 완료/)).toBeInTheDocument();
  });
});

describe("continuing and canceling an import from the menu screen and the home", () => {
  it.each([
    ["processing", "메뉴판 분석 중, 작업 확인하기", true],
    ["ready_for_review", "메뉴 검수 이어서 하기", true],
  ] as const)("shows a %s import on the menu screen and opens it", async (status, text, cancel) => {
    importServer({ job: { status } });
    renderOwnerWeb(MENU_PATH);
    const row = await screen.findByRole("link", { name: text });
    expect(row).toHaveAttribute("href", `/owner${JOB_PATH}`);
    expect(screen.queryByRole("button", { name: "취소하기" }) !== null).toBe(cancel);
    expect(await screen.findByText("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")).toBeInTheDocument();
  });

  it("shows the latest failed import without a cancel, and the menu is not locked", async () => {
    importServer({ job: null, latest: { status: "failed" } });
    renderOwnerWeb(MENU_PATH);
    expect(await screen.findByRole("link", { name: "메뉴판 분석 실패, 다시 확인하기" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "취소하기" })).not.toBeInTheDocument();
    expect(screen.queryByText("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")).not.toBeInTheDocument();
  });

  it("opens the photo picker when there is no import", async () => {
    importServer({ job: null });
    renderOwnerWeb(MENU_PATH);
    expect(await screen.findByRole("link", { name: "메뉴판 사진으로 추가하기" })).toHaveAttribute("href", `/owner/bars/${BAR_ID}/menu/import`);
  });

  it("shows the import on the home's menu card", async () => {
    importServer({ job: { status: "processing" } });
    renderOwnerWeb(`/bars/${BAR_ID}`);
    expect(await screen.findByRole("link", { name: "AI 분석 중, 확인" })).toHaveAttribute("href", `/owner${JOB_PATH}`);
  });

  it("cancels the import after asking, and the menu can be edited again (5.7)", async () => {
    const api = importServer({ job: { status: "processing" } });
    renderOwnerWeb(MENU_PATH);
    await user().click(await screen.findByRole("button", { name: "취소하기" }));
    const sheet = await screen.findByRole("dialog", { name: "메뉴판 사진 등록을 취소할까요?" });
    expect(within(sheet).getByText("선택한 사진과 검수한 내용이 모두 삭제돼요.")).toBeInTheDocument();
    await user().click(within(sheet).getByRole("button", { name: "작업 취소하기" }));
    expect(await screen.findByRole("link", { name: "메뉴판 사진으로 추가하기" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")).not.toBeInTheDocument());
    expect(api.callsTo("POST", `/api/menu-imports/${IMPORT_ID}/cancel`)).toHaveLength(1);
  });

  it.each([
    ["NETWORK_ERROR", "작업 취소에 실패했어요. 인터넷 연결을 확인해 주세요."],
    ["INVALID_IMPORT_STATE", "작업 취소에 실패했어요. 메뉴 등록 상태를 확인해 주세요."],
    ["FORBIDDEN", "이 매장을 관리할 권한이 없어요."],
  ])("leaves the import as it is when the cancel fails (%s)", async (code, message) => {
    importServer({
      job: { status: "processing" },
      answer: (call) =>
        call.path.endsWith("/cancel")
          ? code === "NETWORK_ERROR"
            ? networkFailure()
            : HttpResponse.json(errorBody(code), { status: code === "FORBIDDEN" ? 403 : 409 })
          : undefined,
    });
    renderOwnerWeb(MENU_PATH);
    await user().click(await screen.findByRole("button", { name: "취소하기" }));
    await user().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "작업 취소하기" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "메뉴판 분석 중, 작업 확인하기" })).toBeInTheDocument();
  });
});

describe("reviewing and publishing (spec 5.4, 5.9, 8, PhotoReviewScreen.kt)", () => {
  const card = (name: string) => screen.findByRole("listitem", { name });
  async function resolveReview() {
    const glen = await card("글렌피딕 12년");
    await user().click(within(glen).getByRole("radio", { name: "사진 18,000원" }));
    const added = await card("새 위스키 21년");
    await user().click(within(added).getByRole("button", { name: "이 이름으로 등록" }));
  }

  it("adds the photo's new items after the bar's menu and keeps the other items, their discounts and sold-out marks (partial update E2E)", async () => {
    const api = importServer({ job: { status: "ready_for_review" } });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    expect(await screen.findByText("검수 1/3 완료")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "게시하기" })).toBeDisabled();
    await resolveReview();
    await waitFor(() => expect(screen.getByRole("button", { name: "게시하기" })).toBeEnabled());
    await user().click(screen.getByRole("button", { name: "게시하기" }));
    const sheet = await screen.findByRole("dialog", { name: "이대로 게시할까요?" });
    expect(sheet).toHaveTextContent("기존 가격 변경 1건");
    expect(sheet).toHaveTextContent("연결 없이 등록할 메뉴 1건");
    expect(sheet).toHaveTextContent("기존에 등록된 메뉴는 삭제하지 않아요.");
    await user().click(within(sheet).getByRole("button", { name: "게시하기" }));

    expect(await screen.findByRole("heading", { level: 2, name: "메뉴를 게시했어요." })).toBeInTheDocument();
    expect(screen.getByText("메뉴에 2개를 더했어요.")).toBeInTheDocument();
    expect(screen.getByText("새로 등록한 위스키는 운영자가 확인한 뒤부터 위스키 검색에 나와요.")).toBeInTheDocument();
    const [apply] = api.callsTo("POST", `/api/menu-imports/${IMPORT_ID}/review-and-apply`);
    expect(apply!.body).toEqual({
      reviewVersion: 1,
      itemDecisions: [
        { action: "reject", extractedItemId: "l-head", finalLineType: "section_header" },
        {
          action: "select_existing_product",
          extractedItemId: "l-gf",
          finalLineType: "product",
          productId: P12,
          correctedProductName: null,
          // The 60ml the photo does not show goes back as saved, so the server keeps it and its discount.
          options: [
            { extractedOptionId: "o-gf-30", optionLabel: null, pourMl: 30, priceKrw: 18000 },
            { extractedOptionId: null, optionLabel: null, pourMl: 60, priceKrw: 32000 },
          ],
        },
        { action: "publish_without_product", extractedItemId: "l-new", finalLineType: "product", kind: "whisky", correctedProductName: "새 위스키 21년", options: [{ extractedOptionId: "o-new-30", optionLabel: null, pourMl: 30, priceKrw: 40000 }] },
        { action: "publish_without_product", extractedItemId: "l-sour", finalLineType: "product", kind: "other", correctedProductName: "레몬 사워", options: [{ extractedOptionId: "o-sour", optionLabel: null, pourMl: null, priceKrw: 12000 }] },
      ],
      changeDecisions: [
        { changeId: "c-gf", decision: "apply" },
        { changeId: "c-new", decision: "apply" },
        { changeId: "c-sour", decision: "apply" },
      ],
    });

    // The menu screen, read again: the bar's items first, the new ones added after.
    await user().click(screen.getByRole("link", { name: "메뉴 관리로 돌아가기" }));
    await title("메뉴 관리");
    expect(await screen.findByRole("link", { name: "메뉴판 사진으로 추가하기" })).toBeInTheDocument();
    expect(screen.queryByText("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")).not.toBeInTheDocument();
    expect(api.menu.items.map((item) => [item.displayName, item.soldOut, item.options.map((o) => [o.pourMl, o.priceKrw, o.discount?.discountedPriceKrw ?? null])])).toEqual([
      ["Glenfiddich 12", false, [[30, 18000, null], [60, 32000, 29000]]],
      ["하우스 하이볼", true, [[null, 9000, null]]],
      ["Lagavulin 16", false, [[30, 25000, null]]],
      ["새 위스키 21년", false, [[30, 40000, null]]],
      ["레몬 사워", false, [[null, 12000, null]]],
    ]);
    const glen = await screen.findByRole("link", { name: "Glenfiddich 12 수정" });
    expect(within(glen).getByText("할인")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Lagavulin 16 수정" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "새 위스키 21년 수정" })).toBeInTheDocument();
    for (const head of screen.getAllByRole("button", { expanded: false })) await user().click(head);
    expect(within(await screen.findByRole("link", { name: "하우스 하이볼 수정" })).getByText("품절")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "레몬 사워 수정" })).toBeInTheDocument();
  });

  it("saves the review as a draft and opens it again as it was left", async () => {
    const api = importServer({ job: { status: "ready_for_review" } });
    const first = renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await resolveReview();
    await waitFor(() => expect(api.job!.draftVersion).toBeGreaterThan(0), { timeout: 3000 });
    const saves = api.callsTo("PUT", `/api/menu-imports/${IMPORT_ID}/review-draft`).map((call) => (call.body as { draftVersion: number }).draftVersion);
    expect(saves).toEqual(saves.map((_, i) => i));
    await user().click(screen.getByRole("button", { name: "나중에 하기" }));
    await title("메뉴 관리");
    first.unmount();
    localStorage.clear();

    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await waitFor(() => expect(screen.getByRole("button", { name: "게시하기" })).toBeEnabled());
    expect(screen.getByText("검수 3/3 완료")).toBeInTheDocument();
  });

  it("applies a draft another client saved in the shared format", async () => {
    importServer({
      job: {
        status: "ready_for_review",
        draftVersion: 2,
        draft: {
          draftVersion: 2,
          reviewVersion: 1,
          savedAt: "2026-11-23T00:00:00Z",
          content: {
            itemDecisions: [
              { extractedItemId: "l-gf", action: "select_existing_product", productId: P12, finalLineType: "product", options: [{ extractedOptionId: "o-gf-30", optionLabel: null, pourMl: 30, priceKrw: 17000 }] },
              { extractedItemId: "l-new", action: "publish_without_product", kind: "whisky", finalLineType: "product", correctedProductName: "새 위스키 21년", options: [{ extractedOptionId: "o-new-30", optionLabel: null, pourMl: 30, priceKrw: 40000 }] },
            ],
            clientState: { androidSchemaVersion: 1, androidStateJson: "{}" },
          },
        },
      },
    });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await waitFor(() => expect(screen.getByRole("button", { name: "게시하기" })).toBeEnabled());
    expect(within(await card("글렌피딕 12년")).getByRole("radio", { name: "기존 17,000원" })).toBeChecked();
  });

  it("keeps the edit on this device when the server cannot be reached, and sends it when asked", async () => {
    let offline = true;
    const api = importServer({ job: { status: "ready_for_review" }, answer: (call) => (call.method === "PUT" && offline ? networkFailure() : undefined) });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await user().click(within(await card("새 위스키 21년")).getByRole("button", { name: "이 이름으로 등록" }));
    expect(await screen.findByText("이 기기에는 저장됐어요. 서버 저장을 다시 시도해 주세요.", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(localStorage.getItem(`bottlemap-owner-review:${ME.userId}:${IMPORT_ID}`)).toContain("새 위스키 21년");
    offline = false;
    await user().click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(api.job!.draftVersion).toBe(1));
    await waitFor(() => expect(localStorage.getItem(`bottlemap-owner-review:${ME.userId}:${IMPORT_ID}`)).toBeNull());
  });

  it("opens this device's unsent edit again and sends it", async () => {
    let offline = true;
    const api = importServer({ job: { status: "ready_for_review" }, answer: (call) => (call.method === "PUT" && offline ? networkFailure() : undefined) });
    const first = renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await user().click(within(await card("새 위스키 21년")).getByRole("button", { name: "이 이름으로 등록" }));
    await screen.findByText("이 기기에는 저장됐어요. 서버 저장을 다시 시도해 주세요.", {}, { timeout: 3000 });
    first.unmount();
    offline = false;
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    expect(within(await card("새 위스키 21년")).queryByRole("button", { name: "이 이름으로 등록" })).not.toBeInTheDocument();
    await waitFor(() => expect(api.job!.draftVersion).toBe(1), { timeout: 3000 });
  });

  it("asks which draft to keep when another device saved first (409 REVIEW_DRAFT_OUTDATED)", async () => {
    const api = importServer({ job: { status: "ready_for_review" } });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    api.setJob({ draftVersion: 5, draft: { draftVersion: 5, reviewVersion: 1, savedAt: "2026-11-23T00:00:00Z", content: { itemDecisions: [] } } });
    await user().click(within(await card("새 위스키 21년")).getByRole("button", { name: "이 이름으로 등록" }));
    const sheet = await screen.findByRole("dialog", { name: "다른 곳에서 먼저 저장한 검수 내용이 있어요" }, { timeout: 3000 });
    await user().click(within(sheet).getByRole("button", { name: "이 기기 내용으로 덮어쓰기" }));
    await waitFor(() => expect(api.job!.draftVersion).toBe(6));
    const last = api.callsTo("PUT", `/api/menu-imports/${IMPORT_ID}/review-draft`).at(-1)!;
    expect((last.body as { draftVersion: number }).draftVersion).toBe(5);
  });

  it("opens the review again from the server when another draft is kept", async () => {
    const api = importServer({ job: { status: "ready_for_review" } });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    api.setJob({ draftVersion: 5, draft: { draftVersion: 5, reviewVersion: 1, savedAt: "2026-11-23T00:00:00Z", content: { itemDecisions: [{ extractedItemId: "l-sour", action: "reject" }] } } });
    await user().click(within(await card("새 위스키 21년")).getByRole("button", { name: "이 이름으로 등록" }));
    await user().click(within(await screen.findByRole("dialog", {}, { timeout: 3000 })).getByRole("button", { name: "다른 곳 내용으로 이어 하기" }));
    // The other draft excluded the sour (with the header, two lines); the confirmation made here is gone.
    expect(await screen.findByRole("button", { name: /게시 제외 2/ })).toBeInTheDocument();
    expect(within(await card("새 위스키 21년")).getByRole("button", { name: "이 이름으로 등록" })).toBeInTheDocument();
  });

  it("asks before dropping this device's unsent edit when the review was built again (Codex review on #210)", async () => {
    // This device kept an edit of review version 1 the server never got; the review is now version 2 with an older draft.
    localStorage.setItem(
      `bottlemap-owner-review:${ME.userId}:${IMPORT_ID}`,
      JSON.stringify({
        reviewVersion: 1,
        baseDraftVersion: 0,
        content: {
          itemDecisions: [{ extractedItemId: "l-new", action: "publish_without_product", kind: "whisky", finalLineType: "product", correctedProductName: "새 위스키 21년", options: [{ extractedOptionId: "o-new-30", optionLabel: null, pourMl: 30, priceKrw: 40000 }] }],
          changeDecisions: [],
          clientState: { webSchemaVersion: 1, cards: [], expandedItemIds: [] },
        },
      }),
    );
    const api = importServer({
      job: { status: "ready_for_review", reviewVersion: 2, draftVersion: 3, draft: { draftVersion: 3, reviewVersion: 1, savedAt: "2026-11-23T00:00:00Z", content: { itemDecisions: [] } } },
    });
    renderOwnerWeb(JOB_PATH);
    const sheet = await screen.findByRole("dialog", { name: "다른 곳에서 먼저 저장한 검수 내용이 있어요" });
    await user().click(within(sheet).getByRole("button", { name: "이 기기 내용으로 덮어쓰기" }));
    expect(within(await card("새 위스키 21년")).queryByRole("button", { name: "이 이름으로 등록" })).not.toBeInTheDocument();
    await waitFor(() => expect(api.job!.draftVersion).toBe(4));
    expect((api.callsTo("PUT", `/api/menu-imports/${IMPORT_ID}/review-draft`).at(-1)!.body as { draftVersion: number; reviewVersion: number })).toMatchObject({ draftVersion: 3, reviewVersion: 2 });
  });

  it("saves to the server again once a draft that was too large is changed (Codex review on #210)", async () => {
    let tooLarge = true;
    const api = importServer({
      job: { status: "ready_for_review" },
      answer: (call) => (call.method === "PUT" && tooLarge ? HttpResponse.json({ error: { code: "REVIEW_DRAFT_TOO_LARGE", message: "큼", details: { maxBytes: 262144 }, fieldErrors: [] } }, { status: 413 }) : undefined),
    });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await user().click(within(await card("새 위스키 21년")).getByRole("button", { name: "이 이름으로 등록" }));
    expect(await screen.findByText(/서버 256KB 제한을 초과했어요/)).toBeInTheDocument();
    tooLarge = false;
    await user().click(within(await card("레몬 사워")).getByRole("button", { name: "게시 제외" }));
    await waitFor(() => expect(api.job!.draftVersion).toBe(1));
    await waitFor(() => expect(screen.queryByText(/서버 256KB 제한을 초과했어요/)).not.toBeInTheDocument());
  });

  it("publishes a renamed whisky longer than a catalog search allows without searching (Codex review on #210)", async () => {
    const api = importServer({ job: { status: "ready_for_review" } });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    const longName = `글렌피딕 12년 ${"한정판 ".repeat(25)}`.trim();
    expect(longName.length).toBeGreaterThan(100);
    const glen = await card("글렌피딕 12년");
    await user().click(within(glen).getByRole("button", { name: "메뉴 이름 수정" }));
    const field = within(glen).getByLabelText("메뉴 이름");
    await user().clear(field);
    fireEvent.change(field, { target: { value: longName } });
    await user().click(within(glen).getByRole("button", { name: "저장" }));
    // Spec 7.1 allows 100 characters: like the app, no product matches, so it goes without one, for the operator.
    const renamed = await card(longName);
    expect(within(renamed).getByText("상품 연결 없이 등록해요. 운영자가 확인한 뒤 연결해요.")).toBeInTheDocument();
    expect(screen.queryByText("위스키 검색에 실패했어요. 연결을 유지하고 다시 시도해 주세요.")).not.toBeInTheDocument();
    expect(api.callsTo("GET", "/api/catalog/products")).toHaveLength(0);
    await user().click(within(renamed).getByRole("button", { name: "다른 위스키 검색" }));
    expect(within(await card(longName)).getByLabelText("위스키 이름 검색")).toHaveAttribute("maxLength", "100");
  });

  it("does not claim the edit is kept when this device cannot keep it either, and stays (Codex review on #210)", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    try {
      importServer({ job: { status: "ready_for_review" }, answer: (call) => (call.method === "PUT" ? networkFailure() : undefined) });
      renderOwnerWeb(JOB_PATH);
      await title("메뉴 검수");
      await user().click(within(await card("새 위스키 21년")).getByRole("button", { name: "이 이름으로 등록" }));
      expect(await screen.findByText("서버에도, 이 기기에도 저장하지 못했어요. 화면을 나가면 입력이 사라져요. 서버 저장을 다시 시도해 주세요.")).toBeInTheDocument();
      expect(screen.queryByText("이 기기에는 저장됐어요. 서버 저장을 다시 시도해 주세요.")).not.toBeInTheDocument();
      await user().click(screen.getByRole("button", { name: "나중에 하기" }));
      expect(await screen.findByText("검수 내용을 저장하지 못해 나갈 수 없어요. 서버 저장을 다시 시도해 주세요.")).toBeInTheDocument();
      expect(screen.getByRole("heading", { level: 1, name: "메뉴 검수" })).toBeInTheDocument();
    } finally {
      setItem.mockRestore();
    }
  });

  it("shows a photo URL read after keeping the other draft (Codex review on #210)", async () => {
    const api = importServer({ job: { status: "ready_for_review", imageUrlExpiresAt: "2999-01-01T00:00:00Z" } });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    api.setJob({ draftVersion: 5, imageUrlExpiresAt: "2000-01-01T00:00:00Z", draft: { draftVersion: 5, reviewVersion: 1, savedAt: "2026-11-23T00:00:00Z", content: { itemDecisions: [] } } });
    await user().click(within(await card("새 위스키 21년")).getByRole("button", { name: "이 이름으로 등록" }));
    await user().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "다른 곳 내용으로 이어 하기" }));
    await card("레몬 사워");
    // The response the review reopened from has an expired URL; opening the photo reads a new one.
    api.setJob({ imageUrl: "https://signed.example/photo-1?v=2", imageUrlExpiresAt: "2999-01-01T00:00:00Z" });
    await user().click(within(await card("레몬 사워")).getByRole("button", { name: /원본 사진 크게 보기/ }));
    const sheet = await screen.findByRole("dialog", { name: "원본 사진" });
    await waitFor(() => expect(within(sheet).getByRole("img")).toHaveAttribute("src", "https://signed.example/photo-1?v=2"));
  });

  it("reads the review again when the menu changed meanwhile (409 REVIEW_OUTDATED), keeping the input", async () => {
    const api = importServer({
      job: { status: "ready_for_review" },
      answer: (call) => {
        if (call.path.endsWith("/review-and-apply") && api.job!.reviewVersion === 1) {
          api.setJob({ reviewVersion: 2 });
          return HttpResponse.json(errorBody("REVIEW_OUTDATED"), { status: 409 });
        }
        return undefined;
      },
    });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await resolveReview();
    await waitFor(() => expect(api.job!.draftVersion).toBeGreaterThan(0), { timeout: 3000 });
    await user().click(screen.getByRole("button", { name: "게시하기" }));
    await user().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "게시하기" }));
    expect(await screen.findByText("다른 곳에서 메뉴가 바뀌어 검수 내용을 새로 불러왔어요. 확인한 뒤 다시 게시해 주세요.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "게시하기" })).toBeEnabled());
    await user().click(screen.getByRole("button", { name: "게시하기" }));
    await user().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "게시하기" }));
    expect(await screen.findByRole("heading", { level: 2, name: "메뉴를 게시했어요." })).toBeInTheDocument();
    expect((api.callsTo("POST", `/api/menu-imports/${IMPORT_ID}/review-and-apply`).at(-1)!.body as { reviewVersion: number }).reviewVersion).toBe(2);
  });

  it("names the card of a 422 OPTION_PRICE_CONFLICT", async () => {
    importServer({
      job: { status: "ready_for_review" },
      answer: (call) =>
        call.path.endsWith("/review-and-apply")
          ? HttpResponse.json({ error: { code: "VALIDATION_FAILED", message: "확인", details: null, fieldErrors: [{ path: "itemDecisions[3].options[0]", code: "OPTION_PRICE_CONFLICT", message: "conflict" }] } }, { status: 422 })
          : undefined,
    });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await resolveReview();
    await user().click(screen.getByRole("button", { name: "게시하기" }));
    await user().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "게시하기" }));
    const failed = await screen.findByRole("dialog", { name: "게시하지 못했어요" });
    expect(within(failed).getByRole("alert")).toHaveTextContent("레몬 사워: 같은 메뉴와 용량에 가격이 달라요. 가격을 하나로 맞춰 주세요.");
  });

  it.each([
    ["a lost answer", () => networkFailure()],
    ["a server error", () => HttpResponse.json(errorBody("TEMPORARY_WRITE_CONFLICT"), { status: 503 })],
  ])("reads the import before sending again after %s, and finds it published", async (_, failure) => {
    const api = importServer({
      job: { status: "ready_for_review" },
      answer: (call) => {
        if (!call.path.endsWith("/review-and-apply")) return undefined;
        api.setJob({ status: "applied" });
        return failure();
      },
    });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await resolveReview();
    await user().click(screen.getByRole("button", { name: "게시하기" }));
    await user().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "게시하기" }));
    const unknown = await screen.findByRole("dialog", { name: "게시 결과를 확인하지 못했어요" });
    await user().click(within(unknown).getByRole("button", { name: "게시 상태 확인" }));
    expect(await screen.findByRole("heading", { level: 2, name: "메뉴를 게시했어요." })).toBeInTheDocument();
    expect(api.callsTo("POST", `/api/menu-imports/${IMPORT_ID}/review-and-apply`)).toHaveLength(1);
  });

  it("goes back to the review when the import was not published", async () => {
    let lose = 1;
    const api = importServer({ job: { status: "ready_for_review" }, answer: (call) => (call.path.endsWith("/review-and-apply") && lose-- > 0 ? networkFailure() : undefined) });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await resolveReview();
    await user().click(screen.getByRole("button", { name: "게시하기" }));
    await user().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "게시하기" }));
    await user().click(within(await screen.findByRole("dialog", { name: "게시 결과를 확인하지 못했어요" })).getByRole("button", { name: "게시 상태 확인" }));
    expect(await screen.findByText("게시되지 않았어요. 검수 내용을 확인한 뒤 다시 게시해 주세요.")).toBeInTheDocument();
    expect(api.callsTo("POST", `/api/menu-imports/${IMPORT_ID}/review-and-apply`)).toHaveLength(1);
  });

  it("shows the canceled import when it was canceled elsewhere (409 INVALID_IMPORT_STATE)", async () => {
    const api = importServer({ job: { status: "ready_for_review" } });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await resolveReview();
    api.setJob({ status: "canceled" });
    await user().click(screen.getByRole("button", { name: "게시하기" }));
    await user().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "게시하기" }));
    expect(await screen.findByRole("heading", { level: 2, name: "작업이 취소됐어요" })).toBeInTheDocument();
  });

  it("offers no retry when publishing is forbidden (403)", async () => {
    importServer({ job: { status: "ready_for_review" }, answer: (call) => (call.path.endsWith("/review-and-apply") ? HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 }) : undefined) });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await resolveReview();
    await user().click(screen.getByRole("button", { name: "게시하기" }));
    await user().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "게시하기" }));
    const failed = await screen.findByRole("dialog", { name: "게시하지 못했어요" });
    expect(failed).toHaveTextContent("이 매장을 관리할 권한이 없어요.");
    expect(within(failed).queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
  });

  it("locks the sheet while a slow publish runs and sends it once", async () => {
    const slow = deferred();
    const api = importServer({ job: { status: "ready_for_review" }, answer: async (call) => (call.path.endsWith("/review-and-apply") ? (await slow.gate, undefined) : undefined) });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await resolveReview();
    await user().click(screen.getByRole("button", { name: "게시하기" }));
    const sheet = await screen.findByRole("dialog");
    await user().click(within(sheet).getByRole("button", { name: "게시하기" }));
    await waitFor(() => expect(within(sheet).getByRole("button", { name: "검수로 돌아가기" })).toBeDisabled());
    slow.release();
    expect(await screen.findByRole("heading", { level: 2, name: "메뉴를 게시했어요." })).toBeInTheDocument();
    expect(api.callsTo("POST", `/api/menu-imports/${IMPORT_ID}/review-and-apply`)).toHaveLength(1);
  });

  it("gets a new photo URL from the same GET when it expired, keeping the input (5.4)", async () => {
    const api = importServer({ job: { status: "ready_for_review", imageUrlExpiresAt: "2000-01-01T00:00:00Z" } });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    await user().click(within(await card("새 위스키 21년")).getByRole("button", { name: "이 이름으로 등록" }));
    api.setJob({ imageUrl: "https://signed.example/photo-1?v=2", imageUrlExpiresAt: "2999-01-01T00:00:00Z" });
    await user().click(within(await card("새 위스키 21년")).getByRole("button", { name: /원본 사진 크게 보기/ }));
    const sheet = await screen.findByRole("dialog", { name: "원본 사진" });
    expect(await within(sheet).findByRole("img")).toHaveAttribute("src", "https://signed.example/photo-1?v=2");
    expect(within(await card("새 위스키 21년")).queryByRole("button", { name: "이 이름으로 등록" })).not.toBeInTheDocument();
  });

  it("links a whisky picked from the catalog search, and inactive products cannot be picked (spec 7)", async () => {
    const products = [
      { productId: "p-active", displayName: "New Whisky 21", brandId: "b", brandName: "B", category: "whisky", ageYears: 21, editionName: null, abv: null, isActive: true, matchedAlias: "New Whisky 21" },
      { productId: "p-gone", displayName: "Old Whisky 21", brandId: "b", brandName: "B", category: "whisky", ageYears: 21, editionName: null, abv: null, isActive: false, matchedAlias: "Old Whisky 21" },
    ];
    const api = importServer({ job: { status: "ready_for_review" }, products });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    const added = await card("새 위스키 21년");
    await user().click(within(added).getByRole("button", { name: "위스키 검색" }));
    await user().click(within(added).getByRole("button", { name: "검색" }));
    expect(await within(added).findByRole("radio", { name: "Old Whisky 21 (비활성, 운영자 문의)" })).toBeDisabled();
    await user().click(within(added).getByRole("radio", { name: "New Whisky 21" }));
    await user().click(within(added).getByRole("button", { name: "이 위스키로 선택" }));
    // Linked, it has nothing left to check and moves to "바로 등록할 수 있어요".
    expect(await within(await card("새 위스키 21년")).findByText("연결된 위스키: New Whisky 21")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "바로 등록할 수 있어요" })).getByRole("listitem", { name: "새 위스키 21년" })).toBeInTheDocument();
    expect(api.callsTo("GET", "/api/catalog/products?query=새 위스키 21년")).toHaveLength(1);
  });

  it("saves the bar's default pour and applies it to the glasses that took it", async () => {
    const api = importServer({ job: { status: "ready_for_review", lines: [line({ extractedItemId: "l-gf", proposedProductId: P16, candidates: [candidate(P16, "Lagavulin 16")], extractedProductName: "라가불린 16", options: [lineOption("o-1", "잔", null, 25000)] })] } });
    renderOwnerWeb(JOB_PATH);
    await title("메뉴 검수");
    expect(within(await card("라가불린 16")).getByLabelText("용량 (ml)")).toHaveValue("30");
    await user().type(screen.getByLabelText(/기본 잔 용량/), "45");
    await user().click(screen.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(within(screen.getByRole("listitem", { name: "라가불린 16" })).getByLabelText("용량 (ml)")).toHaveValue("45"));
    expect(api.callsTo("PATCH", `/api/bars/${BAR_ID}`)[0]!.body).toEqual({ defaultPourMl: 45 });
  });
});
