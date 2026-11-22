import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import type { BarMenu, CatalogProduct } from "../owner/queries";
import { bar, barMenu, errorBody, useOwnerApi } from "../test/api";
import { renderOwnerWeb } from "../test/render";
import { server } from "../test/server";
import type { MenuItem } from "./menuRules";

const BAR_ID = "22222222-2222-4222-8222-222222222222";
const GF_ID = "44444444-4444-4444-8444-444444444444";
const LAGA_ID = "55555555-5555-4555-8555-555555555555";
const user = () => userEvent.setup();
const title = (name: string) => screen.findByRole("heading", { level: 1, name });

const option = (id: string, label: string | null, pourMl: number | null, priceKrw: number, discount: MenuItem["options"][number]["discount"] = null) => ({
  menuEntryOptionId: id,
  optionLabel: label,
  pourMl,
  priceKrw,
  discount,
  sortOrder: 1,
});
const item = (overrides: Partial<MenuItem>): MenuItem => ({
  menuBoardEntryId: `entry-${overrides.barMenuItemId ?? "x"}`,
  barMenuItemId: "x",
  productId: null,
  productName: null,
  brandId: null,
  brandName: null,
  category: null,
  kind: "whisky",
  displayName: "",
  sortOrder: 1,
  soldOut: false,
  options: [],
  ...overrides,
});
/** Glenfiddich 12, linked to the catalog, a glass and a bottle (spec 3.9). */
const glenfiddich = item({
  barMenuItemId: "gf-item",
  productId: GF_ID,
  productName: "Glenfiddich 12 Year Old",
  brandId: "brand-gf",
  brandName: "Glenfiddich",
  category: "whisky",
  displayName: "Glenfiddich 12",
  options: [option("gf-glass", "잔", 30, 17000), option("gf-bottle", "병", null, 160000)],
});
/** A whisky without a product, waiting for an operator (spec 3.9). */
const unlinked = item({ barMenuItemId: "local-item", displayName: "위스키 1", options: [option("local-glass", null, 30, 15000)] });
/** A non-whisky item. */
const gintonic = item({ barMenuItemId: "gin-item", kind: "other", displayName: "진토닉", soldOut: true, options: [option("gin-price", null, null, 12000)] });

const catalog = (overrides: Partial<CatalogProduct>): CatalogProduct => ({
  productId: LAGA_ID,
  displayName: "Lagavulin 16 Year Old",
  brandId: "brand-laga",
  brandName: "Lagavulin",
  category: "whisky",
  ageYears: 16,
  editionName: null,
  abv: 43,
  isActive: true,
  matchedAlias: "라가불린 16년",
  ...overrides,
});

type Call = { method: string; path: string; body: Record<string, unknown> | null };
type Answer = (call: Call) => Response | undefined | Promise<Response | undefined>;

/**
 * The bar's menu on a server that keeps the edits of spec 3.14: each success raises `menuVersion`; a request
 * on another version answers 409 MENU_OUTDATED. `answer` may answer first; `apply` false makes it answer
 * without applying.
 */
function menuServer(items: MenuItem[], { answer, products = [], activeMenuImport = null, version = 4 }: { answer?: Answer; products?: CatalogProduct[]; activeMenuImport?: { menuImportId: string; status: "processing" } | null; version?: number | null } = {}) {
  const owned = bar(BAR_ID, "관악 위스키 바", {
    activeMenuImport,
    currentMenu: version === null ? null : { menuBoardId: "board", menuVersion: version, publishedAt: "2026-11-01T03:00:00Z", confirmedAt: null },
  });
  let menu: BarMenu = barMenu(owned, version === null ? {} : { menuBoardId: "board", menuVersion: version, publishedAt: "2026-11-01T03:00:00Z", items });
  const calls: Call[] = [];
  const reads = { menu: 0, bar: 0, myBars: 0 };
  let added = 0;
  useOwnerApi({ bars: [owned] });
  const outdated = (sent: unknown) =>
    sent !== menu.menuVersion
      ? HttpResponse.json({ error: { code: "MENU_OUTDATED", message: "버전", details: { submittedMenuVersion: sent, currentMenuVersion: menu.menuVersion }, fieldErrors: [] } }, { status: 409 })
      : undefined;
  const changed = (next: MenuItem[]) => {
    menu = { ...menu, menuBoardId: "board", menuVersion: (menu.menuVersion ?? 0) + 1, publishedAt: "2026-11-22T03:00:00Z", items: next };
    return menu;
  };
  const record = async (method: string, request: Request, body: Record<string, unknown> | null) => {
    const call = { method, path: new URL(request.url).pathname + new URL(request.url).search, body };
    calls.push(call);
    return answer?.(call);
  };
  server.use(
    http.get("/api/me/bars", () => {
      reads.myBars++;
      return HttpResponse.json({ items: [owned] });
    }),
    http.get("/api/bars/:barId", () => {
      reads.bar++;
      return HttpResponse.json(owned);
    }),
    http.get("/api/bars/:barId/menu", () => {
      reads.menu++;
      return HttpResponse.json(menu);
    }),
    http.get("/api/catalog/products", ({ request }) => {
      const query = new URL(request.url).searchParams.get("query") ?? "";
      calls.push({ method: "GET", path: `/api/catalog/products?query=${query}`, body: null });
      return HttpResponse.json({ items: products });
    }),
    http.get("/api/catalog/brands", () => HttpResponse.json({ items: [] })),
    http.post("/api/bars/:barId/menu/items", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      const custom = await record("POST", request, body);
      if (custom) return custom;
      const stale = outdated(body.menuVersion);
      if (stale) return stale;
      const found = products.find((product) => product.productId === body.productId);
      added++;
      const created = item({
        barMenuItemId: `added-${added}`,
        productId: (body.productId as string | undefined) ?? null,
        productName: found?.displayName ?? null,
        brandId: found?.brandId ?? null,
        brandName: found?.brandName ?? null,
        category: found ? "whisky" : null,
        kind: (body.kind as "whisky" | "other" | undefined) ?? "whisky",
        displayName: body.displayName as string,
        options: (body.options as MenuItem["options"]).map((sent, index) => ({ ...option(`added-${added}-${index}`, null, null, 0), ...sent, discount: sent.discount ?? null })),
      });
      return HttpResponse.json(changed([...menu.items, created]), { status: 201 });
    }),
    http.put("/api/bars/:barId/menu/items/:itemId", async ({ request, params }) => {
      const body = (await request.json()) as Record<string, unknown>;
      const custom = await record("PUT", request, body);
      if (custom) return custom;
      const stale = outdated(body.menuVersion);
      if (stale) return stale;
      return HttpResponse.json(
        changed(
          menu.items.map((entry) =>
            entry.barMenuItemId === params.itemId
              ? { ...entry, displayName: body.displayName as string, options: (body.options as MenuItem["options"]).map((sent, index) => ({ ...option(`edited-${index}`, null, null, 0), ...sent, discount: sent.discount ?? null })) }
              : entry,
          ),
        ),
      );
    }),
    http.delete("/api/bars/:barId/menu/items/:itemId", async ({ request, params }) => {
      const custom = await record("DELETE", request, null);
      if (custom) return custom;
      const stale = outdated(Number(new URL(request.url).searchParams.get("menuVersion")));
      if (stale) return stale;
      return HttpResponse.json(changed(menu.items.filter((entry) => entry.barMenuItemId !== params.itemId)));
    }),
    http.post("/api/bars/:barId/menu/reset", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      const custom = await record("POST reset", request, body);
      if (custom) return custom;
      const stale = outdated(body.menuVersion);
      if (stale) return stale;
      return HttpResponse.json(changed([]));
    }),
  );
  return {
    calls,
    writes: () => calls.filter((call) => call.method !== "GET"),
    reads,
    menu: () => menu,
    /** Changes the menu as another device would. */
    changeElsewhere: (next: MenuItem[]) => changed(next),
  };
}

async function openMenu() {
  const view = renderOwnerWeb(`/bars/${BAR_ID}/menu`);
  await title("메뉴 관리");
  await screen.findByRole("heading", { name: "현재 게시 메뉴" });
  return view;
}

async function openAdd() {
  const view = renderOwnerWeb(`/bars/${BAR_ID}/menu/new`);
  await title("메뉴 직접 추가");
  await screen.findByLabelText("메뉴 이름");
  return view;
}

async function openEdit(itemId: string) {
  const view = renderOwnerWeb(`/bars/${BAR_ID}/menu/${itemId}`);
  await title("메뉴 수정");
  await screen.findByLabelText("메뉴 이름");
  return view;
}

const optionGroup = (index: number) => screen.getByRole("group", { name: new RegExp(`^${index}번 옵션`) });
async function fillOption(index: number, ml: string | null, price: string) {
  const group = optionGroup(index);
  if (ml === null) await user().click(within(group).getByRole("checkbox", { name: "Bottle 판매" }));
  else await user().type(within(group).getByLabelText("용량 (ml)"), ml);
  await user().type(within(group).getByLabelText("가격 (원)"), price);
}
const save = (name = "메뉴 추가") => user().click(screen.getByRole("button", { name }));
const atMenuList = async (router: { state: { location: { pathname: string } } }) =>
  waitFor(() => expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/menu`));

describe("the menu list (OwnerManualMenuScreen.kt, spec 3.9)", () => {
  it("lists whisky by brand and the rest by kind, with prices, sale status, count and last update", async () => {
    menuServer([glenfiddich, unlinked, gintonic]);
    await openMenu();

    expect(screen.getByText(/전체 3개/)).toHaveTextContent("최근 갱신 11.01");
    const whisky = screen.getByRole("region", { name: "위스키" });
    expect(within(whisky).getByRole("heading", { name: "Glenfiddich" })).toBeInTheDocument();
    expect(within(whisky).getByRole("heading", { name: "기타 브랜드" })).toBeInTheDocument();
    const gf = within(whisky).getByRole("link", { name: "Glenfiddich 12 수정" });
    // The brand is left out of a whisky's name under its brand (manualMenuShortName).
    expect(gf).toHaveTextContent("12");
    expect(gf).toHaveTextContent("30ml17,000원");
    expect(gf).toHaveTextContent("Bottle160,000원");
    expect(gf).toHaveTextContent("판매 중");
    // Other kinds start folded, as in the app.
    const other = screen.getByRole("region", { name: "기타 주류" });
    await user().click(within(other).getByRole("button", { name: /기타 주류/ }));
    expect(within(other).getByRole("link", { name: "진토닉 수정" })).toHaveTextContent("품절");
  });

  it("searches the menu's own items, whatever the spacing", async () => {
    menuServer([glenfiddich, unlinked, gintonic]);
    await openMenu();

    await user().type(screen.getByLabelText("메뉴 검색"), "위스키1");
    expect(screen.getByText(/1개 검색됨/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "위스키 1 수정" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Glenfiddich 12 수정" })).not.toBeInTheDocument();

    await user().clear(screen.getByLabelText("메뉴 검색"));
    await user().type(screen.getByLabelText("메뉴 검색"), "없는 메뉴");
    expect(screen.getByText("검색 결과가 없어요.")).toBeInTheDocument();
  });

  it("shows the empty menu with a first add (spec 3.9.1)", async () => {
    menuServer([], { version: null });
    const { router } = await openMenu();

    expect(screen.getByText("등록된 메뉴가 없어요.")).toBeInTheDocument();
    await user().click(screen.getByRole("link", { name: "첫 메뉴 추가하기" }));
    await title("메뉴 직접 추가");
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/menu/new`);
  });

  it("shows an error with a retry, and the bar list when the bar is gone", async () => {
    let failures = 1;
    menuServer([glenfiddich]);
    server.use(http.get("/api/bars/:barId/menu", () => (failures-- > 0 ? HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 }) : undefined)));
    renderOwnerWeb(`/bars/${BAR_ID}/menu`);

    await user().click(await screen.findByRole("button", { name: "다시 시도" }));
    expect(await screen.findByRole("link", { name: "Glenfiddich 12 수정" })).toBeInTheDocument();
  });

  it("offers the bar list when the bar is gone (404 BAR_NOT_FOUND)", async () => {
    menuServer([glenfiddich]);
    server.use(http.get("/api/bars/:barId/menu", () => HttpResponse.json(errorBody("BAR_NOT_FOUND"), { status: 404 })));
    renderOwnerWeb(`/bars/${BAR_ID}/menu`);

    expect(await screen.findByText("매장을 찾을 수 없어요.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "내 매장 목록으로" })).toBeInTheDocument();
  });

  it("shows loading while the menu is slow", async () => {
    let answer: (() => void) | null = null;
    menuServer([glenfiddich]);
    server.use(
      http.get("/api/bars/:barId/menu", async () => {
        await new Promise<void>((resolve) => (answer = resolve));
        return undefined;
      }),
    );
    renderOwnerWeb(`/bars/${BAR_ID}/menu`);

    expect(await screen.findByText("매장 정보를 불러오고 있어요.")).toBeInTheDocument();
    await waitFor(() => expect(answer).not.toBeNull());
    answer!();
    expect(await screen.findByRole("link", { name: "Glenfiddich 12 수정" })).toBeInTheDocument();
  });

  it("locks every change while a menu photo import is unfinished (spec 3.14.7)", async () => {
    menuServer([glenfiddich], { activeMenuImport: { menuImportId: "import", status: "processing" } });
    await openMenu();

    expect(await screen.findByText("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")).toBeInTheDocument();
    expect(screen.getByText("사진 등록 중, 편집 불가")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Glenfiddich 12 수정" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+ 직접 추가" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("button", { name: "전체 메뉴 초기화" })).toBeDisabled();
  });

  it("does not open an item with four or more options, as the app", async () => {
    const four = item({ barMenuItemId: "four", productId: GF_ID, brandName: "Glenfiddich", displayName: "Glenfiddich 18", category: "whisky", options: [15, 30, 45, 60].map((ml) => option(`o${ml}`, null, ml, ml * 1000)) });
    menuServer([four]);
    const { router } = await openMenu();

    await user().click(screen.getByRole("button", { name: "Glenfiddich 18 수정" }));
    expect(screen.getByText("이 메뉴는 가격 옵션이 4개 이상이어서 직접 수정할 수 없어요. 기존 메뉴는 유지됩니다.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/menu`);
  });

  it("empties the menu after asking, and reads the menu, the bar and the bar list again (spec 3.14.6)", async () => {
    const api = menuServer([glenfiddich, unlinked]);
    await openMenu();

    await user().click(screen.getByRole("button", { name: "전체 메뉴 초기화" }));
    const sheet = screen.getByRole("dialog", { name: "전체 메뉴를 초기화할까요?" });
    expect(within(sheet).getByText("모든 메뉴와 용량, 가격 정보가 삭제됩니다.")).toBeInTheDocument();
    await user().click(within(sheet).getByRole("button", { name: "취소" }));
    expect(api.writes()).toEqual([]);

    const reads = { ...api.reads };
    await user().click(screen.getByRole("button", { name: "전체 메뉴 초기화" }));
    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "초기화" }));

    expect(await screen.findByText("등록된 메뉴가 없어요.")).toBeInTheDocument();
    expect(api.writes()).toEqual([{ method: "POST reset", path: `/api/bars/${BAR_ID}/menu/reset`, body: { menuVersion: 4 } }]);
    await waitFor(() => expect(api.reads.myBars).toBeGreaterThan(reads.myBars));
    expect(api.reads.bar).toBeGreaterThan(reads.bar);
  });

  it("says so in the sheet when the menu changed elsewhere, and resets the new version next", async () => {
    const api = menuServer([glenfiddich]);
    await openMenu();
    api.changeElsewhere([glenfiddich, unlinked]);

    await user().click(screen.getByRole("button", { name: "전체 메뉴 초기화" }));
    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "초기화" }));
    expect(await within(screen.getByRole("dialog")).findByText("메뉴가 다른 곳에서 바뀌었어요. 확인한 뒤 다시 시도해 주세요.")).toBeInTheDocument();
    expect(await screen.findByText(/전체 2개/)).toBeInTheDocument();

    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "초기화" }));
    expect(await screen.findByText("등록된 메뉴가 없어요.")).toBeInTheDocument();
    expect(api.writes().map((call) => call.body)).toEqual([{ menuVersion: 4 }, { menuVersion: 5 }]);
  });
});

describe("the home menu card (OwnerManagementHomeScreen.kt)", () => {
  it("shows the item count and the later of the publish and the confirmation", async () => {
    menuServer([glenfiddich, unlinked, gintonic]);
    server.use(
      http.get("/api/bars/:barId", () =>
        HttpResponse.json(bar(BAR_ID, "관악 위스키 바", { currentMenu: { menuBoardId: "board", menuVersion: 4, publishedAt: "2026-11-01T03:00:00Z", confirmedAt: "2026-11-20T03:00:00Z" } })),
      ),
    );
    const { router } = renderOwnerWeb(`/bars/${BAR_ID}`);

    const card = await screen.findByRole("link", { name: /메뉴 관리/ });
    await waitFor(() => expect(card).toHaveTextContent("게시된 메뉴 3개, 최근 갱신 11.20"));
    await user().click(card);
    await title("메뉴 관리");
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/menu`);
  });
});

describe("the home menu card while its menu is loading or failed", () => {
  it("says the count is loading, then that it could not be read", async () => {
    let answer: (() => void) | null = null;
    menuServer([glenfiddich]);
    server.use(
      http.get("/api/bars/:barId/menu", async () => {
        await new Promise<void>((resolve) => (answer = resolve));
        return HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 });
      }),
    );
    renderOwnerWeb(`/bars/${BAR_ID}`);

    const card = await screen.findByRole("link", { name: /메뉴 관리/ });
    expect(card).toHaveTextContent("게시된 메뉴 불러오는 중, 최근 갱신 11.01");
    await waitFor(() => expect(answer).not.toBeNull());
    answer!();
    await waitFor(() => expect(card).toHaveTextContent("메뉴 개수를 불러오지 못했어요, 최근 갱신 11.01"));
  });
});

describe("adding an item (spec 3.14.3, OwnerManualCatalogMatch.kt)", () => {
  it("links a proposed catalog product only after 맞아요, and sends its productId", async () => {
    const api = menuServer([unlinked], { products: [catalog({})] });
    const { router } = await openAdd();

    await user().type(screen.getByLabelText("메뉴 이름"), "라가불린 16년");
    const proposal = await screen.findByRole("group", { name: "상품 확인" });
    expect(proposal).toHaveTextContent("“Lagavulin 16 Year Old”이 맞나요?");
    await user().click(within(proposal).getByRole("button", { name: "맞아요" }));
    expect(screen.getByLabelText("메뉴 이름")).toHaveValue("Lagavulin 16 Year Old");
    expect(screen.queryByRole("group", { name: "상품 확인" })).not.toBeInTheDocument();

    await fillOption(1, "30", "22000");
    await user().click(screen.getByRole("button", { name: "+ 용량 옵션 추가" }));
    await fillOption(2, null, "210000");
    await save();

    await atMenuList(router);
    expect(api.writes()).toEqual([
      {
        method: "POST",
        path: `/api/bars/${BAR_ID}/menu/items`,
        body: {
          menuVersion: 4,
          displayName: "Lagavulin 16 Year Old",
          options: [
            { optionLabel: null, pourMl: 30, priceKrw: 22000, discount: null },
            { optionLabel: "Bottle", pourMl: null, priceKrw: 210000, discount: null },
          ],
          productId: LAGA_ID,
        },
      },
    ]);
    expect(await screen.findByRole("link", { name: "Lagavulin 16 Year Old 수정" })).toBeInTheDocument();
  });

  it("keeps a confirmed product when the name is changed and a later search no longer finds it", async () => {
    // Codex review on #199: the link is kept on its own, not looked up again in the latest results.
    const api = menuServer([], { products: [catalog({})] });
    const searched: string[] = [];
    server.use(
      http.get("/api/catalog/products", ({ request }) => {
        const query = new URL(request.url).searchParams.get("query") ?? "";
        searched.push(query);
        return HttpResponse.json({ items: ["라가불린 16년", "Lagavulin 16 Year Old"].includes(query) ? [catalog({})] : [] });
      }),
    );
    const { router } = await openAdd();
    await user().type(screen.getByLabelText("메뉴 이름"), "라가불린 16년");
    await user().click(within(await screen.findByRole("group", { name: "상품 확인" })).getByRole("button", { name: "맞아요" }));

    await user().clear(screen.getByLabelText("메뉴 이름"));
    await user().type(screen.getByLabelText("메뉴 이름"), "라가불린 16 시그니처");
    await waitFor(() => expect(searched).toContain("라가불린 16 시그니처"));
    await fillOption(1, "30", "22000");
    await save();

    await atMenuList(router);
    expect(api.writes()[0]?.body).toMatchObject({ displayName: "라가불린 16 시그니처", productId: LAGA_ID });
    expect(api.writes()[0]?.body).not.toHaveProperty("kind");
  });

  it("asks to answer the proposal first, and adds without a product after 아니에요", async () => {
    const api = menuServer([], { products: [catalog({})] });
    const { router } = await openAdd();
    await user().type(screen.getByLabelText("메뉴 이름"), "라가불린 16년");
    await screen.findByRole("group", { name: "상품 확인" });
    await fillOption(1, "30", "22000");

    // Saving without an answer: the app searches once more and asks first.
    await save();
    expect(await screen.findByText("“Lagavulin 16 Year Old”이 맞나요? 맞아요 또는 아니에요를 선택해 주세요.")).toBeInTheDocument();
    expect(api.writes()).toEqual([]);

    await user().click(screen.getByRole("button", { name: "아니에요" }));
    await save();

    await atMenuList(router);
    expect(api.writes()[0]?.body).toEqual({ menuVersion: 4, displayName: "라가불린 16년", options: [{ optionLabel: null, pourMl: 30, priceKrw: 22000, discount: null }], kind: "whisky" });
  });

  it("names an inactive product and refuses to add it (spec 7.2)", async () => {
    const api = menuServer([], { products: [catalog({ isActive: false })] });
    await openAdd();

    await user().type(screen.getByLabelText("메뉴 이름"), "라가불린 16년");
    expect(await screen.findByText("“Lagavulin 16 Year Old”은 현재 비활성 상품이에요. 선택하거나 새로 만들 수 없어요. 운영자에게 문의해 주세요.")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "상품 확인" })).not.toBeInTheDocument();
    await fillOption(1, "30", "22000");
    await save();

    expect(screen.getByText("운영이 중지된 카탈로그 상품이에요. 운영자에게 문의해 주세요.")).toBeInTheDocument();
    expect(api.writes()).toEqual([]);
  });

  it("adds a non-whisky item with one price and kind other, without searching the catalog", async () => {
    const api = menuServer([]);
    const { router } = await openAdd();

    await user().selectOptions(screen.getByLabelText("종류"), "칵테일");
    await user().type(screen.getByLabelText("메뉴 이름"), "하이볼");
    expect(screen.queryByRole("button", { name: "+ 용량 옵션 추가" })).not.toBeInTheDocument();
    await user().type(screen.getByLabelText("판매 가격 (원)"), "12,000");
    await save();

    await atMenuList(router);
    expect(api.calls.filter((call) => call.path.startsWith("/api/catalog"))).toEqual([]);
    expect(api.writes()[0]?.body).toEqual({ menuVersion: 4, displayName: "하이볼", options: [{ optionLabel: null, pourMl: null, priceKrw: 12000, discount: null }], kind: "other" });
  });

  it("sends menuVersion null for the first item of a bar without a menu (spec 3.14.1)", async () => {
    const api = menuServer([], { version: null });
    const { router } = await openAdd();

    await user().selectOptions(screen.getByLabelText("종류"), "안주");
    await user().type(screen.getByLabelText("메뉴 이름"), "치즈 플레이트");
    await user().type(screen.getByLabelText("판매 가격 (원)"), "18000");
    await save();

    await atMenuList(router);
    expect(api.writes()[0]?.body).toMatchObject({ menuVersion: null, kind: "other" });
  });

  it("points to the item already on the menu for a confirmed product", async () => {
    const api = menuServer([glenfiddich], { products: [catalog({ productId: GF_ID, displayName: "Glenfiddich 12 Year Old", brandId: "brand-gf", brandName: "Glenfiddich", ageYears: 12, matchedAlias: "글렌피딕 12년" })] });
    const { router } = await openAdd();

    await user().type(screen.getByLabelText("메뉴 이름"), "글렌피딕 12년");
    await user().click(within(await screen.findByRole("group", { name: "상품 확인" })).getByRole("button", { name: "맞아요" }));
    await user().click(screen.getByRole("button", { name: "기존 메뉴에서 용량, 가격 수정" }));

    await title("메뉴 수정");
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/menu/gf-item`);
    expect(screen.getByLabelText("메뉴 이름")).toHaveValue("Glenfiddich 12");
    expect(api.writes()).toEqual([]);
  });

  it("checks the options before sending, with the app's messages", async () => {
    const api = menuServer([]);
    await openAdd();
    await user().type(screen.getByLabelText("메뉴 이름"), "위스키 2");

    await user().type(within(optionGroup(1)).getByLabelText("가격 (원)"), "15000");
    await save();
    expect(screen.getByText("용량을 입력하거나 Bottle 판매를 선택해 주세요.")).toBeInTheDocument();

    await user().type(within(optionGroup(1)).getByLabelText("용량 (ml)"), "30");
    await user().click(screen.getByRole("button", { name: "+ 용량 옵션 추가" }));
    await fillOption(2, "30", "20000");
    await save();
    expect(screen.getByText("같은 제품에 동일한 용량 옵션을 중복 등록할 수 없어요.")).toBeInTheDocument();

    await user().click(screen.getByRole("button", { name: "+ 용량 옵션 추가" }));
    expect(screen.getByText("가격 옵션은 최대 3개까지 등록할 수 있어요.")).toBeInTheDocument();
    expect(api.writes()).toEqual([]);
  });

  it("shows the server's errors under the name and the options they are about (422)", async () => {
    menuServer([], {
      answer: ({ method }) =>
        method === "POST"
          ? HttpResponse.json(
              {
                error: {
                  code: "VALIDATION_FAILED",
                  message: "입력",
                  details: null,
                  fieldErrors: [
                    { path: "displayName", code: "NOT_NORMALIZABLE", message: "이름" },
                    { path: "options", code: "DUPLICATE_OPTION_VALUES", message: "중복" },
                    { path: "options[0].priceKrw", code: "LESS_THAN_EQUAL", message: "가격" },
                  ],
                },
              },
              { status: 422 },
            )
          : undefined,
    });
    await openAdd();
    await user().type(screen.getByLabelText("메뉴 이름"), "★★");
    await fillOption(1, "30", "15000");
    await save();

    expect(await screen.findByText("메뉴 이름에 쓸 수 있는 글자가 없어요.")).toBeInTheDocument();
    expect(within(optionGroup(1)).getByText("허용 범위보다 커요.")).toBeInTheDocument();
    // DUPLICATE_OPTION_VALUES names the list (backend menu_edit.py), so it goes under the options.
    expect(within(screen.getByRole("region", { name: "용량별 가격" })).getByText("같은 제품에 동일한 용량 옵션을 중복 등록할 수 없어요.")).toBeInTheDocument();
    expect(screen.getByText("입력한 내용을 확인해 주세요.")).toBeInTheDocument();
  });

  it("shows a product made inactive meanwhile under the name (422 PRODUCT_INACTIVE)", async () => {
    menuServer([], {
      products: [catalog({})],
      answer: ({ method }) =>
        method === "POST"
          ? HttpResponse.json({ error: { code: "VALIDATION_FAILED", message: "비활성", details: null, fieldErrors: [{ path: "productId", code: "PRODUCT_INACTIVE", message: "비활성" }] } }, { status: 422 })
          : undefined,
    });
    await openAdd();
    await user().type(screen.getByLabelText("메뉴 이름"), "라가불린 16년");
    await user().click(within(await screen.findByRole("group", { name: "상품 확인" })).getByRole("button", { name: "맞아요" }));
    await fillOption(1, "30", "22000");
    await save();

    expect(await screen.findByText("운영이 중지된 카탈로그 상품이에요. 운영자에게 문의해 주세요.")).toBeInTheDocument();
    expect(screen.getByLabelText("메뉴 이름")).toHaveAccessibleDescription("운영이 중지된 카탈로그 상품이에요. 운영자에게 문의해 주세요.");
  });

  it("opens the item already there when the server says so (409 MENU_ITEM_EXISTS)", async () => {
    menuServer([unlinked], {
      answer: ({ method }) =>
        method === "POST"
          ? HttpResponse.json({ error: { code: "MENU_ITEM_EXISTS", message: "있음", details: { barMenuItemId: "local-item" }, fieldErrors: [] } }, { status: 409 })
          : undefined,
    });
    const { router } = await openAdd();
    await user().type(screen.getByLabelText("메뉴 이름"), "위스키 3");
    await fillOption(1, "30", "15000");
    await save();

    expect(await screen.findByText("이미 등록한 상품이에요. 기존 메뉴에서 용량, 가격을 수정해 주세요.")).toBeInTheDocument();
    await user().click(screen.getByRole("button", { name: "기존 메뉴에서 용량, 가격 수정" }));
    await title("메뉴 수정");
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/menu/local-item`);
  });

  it("locks the editor without a retry when an import started (409 ACTIVE_IMPORT_EXISTS)", async () => {
    let importing = false;
    const api = menuServer([], {
      answer: ({ method }) => {
        if (method !== "POST") return undefined;
        importing = true;
        return HttpResponse.json({ error: { code: "ACTIVE_IMPORT_EXISTS", message: "작업", details: { menuImportId: "import", status: "processing" }, fieldErrors: [] } }, { status: 409 });
      },
    });
    server.use(http.get("/api/bars/:barId", () => HttpResponse.json(bar(BAR_ID, "관악 위스키 바", { activeMenuImport: importing ? { menuImportId: "import", status: "processing" } : null }))));
    await openAdd();
    await user().type(screen.getByLabelText("메뉴 이름"), "위스키 3");
    await fillOption(1, "30", "15000");
    await save();

    expect(await screen.findAllByText("사진으로 메뉴 등록 작업 중에는 메뉴를 수정할 수 없어요.")).not.toHaveLength(0);
    await waitFor(() => expect(screen.getByLabelText("메뉴 이름")).toBeDisabled());
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    expect(api.writes()).toHaveLength(1);
  });

  it("keeps the input after a change elsewhere, and saves on the new version (409 MENU_OUTDATED)", async () => {
    const api = menuServer([glenfiddich]);
    const { router } = await openAdd();
    api.changeElsewhere([glenfiddich, gintonic]);
    await user().type(screen.getByLabelText("메뉴 이름"), "위스키 3");
    await fillOption(1, "30", "15000");
    await save();

    expect(await screen.findByText("메뉴가 다른 곳에서 바뀌었어요. 확인한 뒤 다시 저장해 주세요.")).toBeInTheDocument();
    expect(screen.getByLabelText("메뉴 이름")).toHaveValue("위스키 3");
    await save();

    await atMenuList(router);
    expect(api.writes().map((call) => call.body?.menuVersion)).toEqual([4, 5]);
  });

  it("counts a resent add as done when its lost answer had been applied (spec 3.14.1)", async () => {
    let lose = true;
    const api = menuServer([glenfiddich], {
      answer: ({ method }) => {
        if (method !== "POST" || !lose) return undefined;
        lose = false;
        // The server adds the item, and the answer is lost on the way back.
        api.changeElsewhere([glenfiddich, item({ barMenuItemId: "added-lost", displayName: "위스키 3", options: [option("lost-0", null, 30, 15000)] })]);
        return HttpResponse.error();
      },
    });
    const { router } = await openAdd();
    await user().type(screen.getByLabelText("메뉴 이름"), "위스키 3");
    await fillOption(1, "30", "15000");
    await save();
    expect(await screen.findByText("서버에 연결하지 못했어요. 네트워크를 확인해 주세요.")).toBeInTheDocument();

    await save();

    await atMenuList(router);
    // The resend went with the first version, got MENU_OUTDATED, and the menu read again held the item.
    expect(api.writes().map((call) => call.body?.menuVersion)).toEqual([4, 4]);
    expect(api.menu().items.filter((entry) => entry.displayName === "위스키 3")).toHaveLength(1);
    expect(await screen.findByRole("link", { name: "위스키 3 수정" })).toBeInTheDocument();
  });

  it("asks again when a resent add had not been applied, and the menu changed meanwhile", async () => {
    let lose = true;
    const api = menuServer([glenfiddich], {
      answer: ({ method }) => {
        if (method !== "POST" || !lose) return undefined;
        lose = false;
        return HttpResponse.error();
      },
    });
    await openAdd();
    await user().type(screen.getByLabelText("메뉴 이름"), "위스키 3");
    await fillOption(1, "30", "15000");
    await save();
    await screen.findByText("서버에 연결하지 못했어요. 네트워크를 확인해 주세요.");
    api.changeElsewhere([glenfiddich, gintonic]);

    await save();

    expect(await screen.findByText("메뉴가 다른 곳에서 바뀌었어요. 확인한 뒤 다시 저장해 주세요.")).toBeInTheDocument();
    expect(api.menu().items.map((entry) => entry.displayName)).toEqual(["Glenfiddich 12", "진토닉"]);
  });
});

describe("editing an item (spec 3.14.4, 3.14.5)", () => {
  it("opens with the menu name and options only, and sends them with the saved discount", async () => {
    const running = { discountedPriceKrw: 14000, startsAt: "2026-11-01T00:00:00Z", endsAt: "2099-12-01T00:00:00Z" };
    const discounted = { ...glenfiddich, options: [option("gf-glass", "잔", 30, 17000, running), option("gf-bottle", "병", null, 160000)] };
    const api = menuServer([discounted, unlinked]);
    const { router } = await openEdit("gf-item");

    expect(screen.getByLabelText("메뉴 이름")).toHaveValue("Glenfiddich 12");
    expect(screen.queryByLabelText("종류")).not.toBeInTheDocument();
    expect(screen.queryByText(/Glenfiddich 12 Year Old/)).not.toBeInTheDocument();
    expect(optionGroup(1)).toHaveTextContent("할인 14,000원");
    expect(within(optionGroup(2)).getByRole("checkbox", { name: "Bottle 판매" })).toBeChecked();

    await user().clear(screen.getByLabelText("메뉴 이름"));
    await user().type(screen.getByLabelText("메뉴 이름"), "글렌피딕 12년");
    await user().clear(within(optionGroup(2)).getByLabelText("가격 (원)"));
    await user().type(within(optionGroup(2)).getByLabelText("가격 (원)"), "170000");
    await save("저장하기");

    await atMenuList(router);
    expect(api.writes()).toEqual([
      {
        method: "PUT",
        path: `/api/bars/${BAR_ID}/menu/items/gf-item`,
        body: {
          menuVersion: 4,
          displayName: "글렌피딕 12년",
          // The saved labels stay ("잔", "병"), and the discount is sent back so it is kept.
          options: [
            { optionLabel: "잔", pourMl: 30, priceKrw: 17000, discount: running },
            { optionLabel: "병", pourMl: null, priceKrw: 170000, discount: null },
          ],
        },
      },
    ]);
  });

  it("leaves out a discount that has ended (spec 3.14.2)", async () => {
    const ended = { discountedPriceKrw: 14000, startsAt: "2026-01-01T00:00:00Z", endsAt: "2026-01-02T00:00:00Z" };
    const api = menuServer([{ ...glenfiddich, options: [option("gf-glass", "잔", 30, 17000, ended)] }]);
    const { router } = await openEdit("gf-item");

    await save("저장하기");

    await atMenuList(router);
    expect(api.writes()[0]?.body?.options).toEqual([{ optionLabel: "잔", pourMl: 30, priceKrw: 17000, discount: null }]);
  });

  it("says a discount ended under its option, and leaves it out on the next save (422 DISCOUNT_ENDED)", async () => {
    // Running when the editor opened; the server's clock says it has ended.
    const running = { discountedPriceKrw: 14000, startsAt: "2026-11-01T00:00:00Z", endsAt: "2099-12-01T00:00:00Z" };
    let ended = false;
    const api = menuServer([{ ...glenfiddich, options: [option("gf-glass", "잔", 30, 17000, running)] }], {
      answer: ({ method }) => {
        if (method !== "PUT" || ended) return undefined;
        ended = true;
        return HttpResponse.json(
          { error: { code: "VALIDATION_FAILED", message: "끝남", details: null, fieldErrors: [{ path: "options[0].discount.endsAt", code: "DISCOUNT_ENDED", message: "끝남" }] } },
          { status: 422 },
        );
      },
    });
    await openEdit("gf-item");
    await save("저장하기");

    expect(await within(optionGroup(1)).findByText("할인 기간이 끝났어요. 다시 저장해 주세요.")).toBeInTheDocument();
    await waitFor(() => expect(api.reads.menu).toBeGreaterThan(1));
    expect(optionGroup(1)).not.toHaveTextContent("할인 14,000원");
    await save("저장하기");

    await waitFor(() => expect(api.writes()).toHaveLength(2));
    expect(api.writes().map((call) => (call.body?.options as { discount: unknown }[])[0]?.discount)).toEqual([running, null]);
  });

  it("deletes after asking (spec 3.14.5)", async () => {
    const api = menuServer([glenfiddich, unlinked]);
    const { router } = await openEdit("local-item");

    await user().click(screen.getByRole("button", { name: "삭제" }));
    const sheet = screen.getByRole("dialog", { name: "메뉴를 삭제할까요?" });
    expect(within(sheet).getByText("삭제하면 고객 메뉴에서도 바로 사라집니다.")).toBeInTheDocument();
    await user().click(within(sheet).getByRole("button", { name: "취소" }));
    expect(api.writes()).toEqual([]);

    await user().click(screen.getByRole("button", { name: "삭제" }));
    await user().click(within(screen.getByRole("dialog", { name: "메뉴를 삭제할까요?" })).getByRole("button", { name: "삭제하기" }));

    await atMenuList(router);
    expect(api.writes()).toEqual([{ method: "DELETE", path: `/api/bars/${BAR_ID}/menu/items/local-item?menuVersion=4`, body: null }]);
    expect(await screen.findByText(/전체 1개/)).toBeInTheDocument();
  });

  it("counts a resent delete as done when the item is already gone", async () => {
    let lose = true;
    const api = menuServer([glenfiddich, unlinked], {
      answer: ({ method }) => {
        if (method !== "DELETE" || !lose) return undefined;
        lose = false;
        // Deleted on the server; the answer is lost.
        api.changeElsewhere([glenfiddich]);
        return HttpResponse.error();
      },
    });
    const { router } = await openEdit("local-item");

    await user().click(screen.getByRole("button", { name: "삭제" }));
    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "삭제하기" }));
    expect(await within(screen.getByRole("dialog")).findByText("서버에 연결하지 못했어요. 네트워크를 확인해 주세요.")).toBeInTheDocument();
    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "삭제하기" }));

    await atMenuList(router);
    expect(api.writes().map((call) => call.path)).toEqual([`/api/bars/${BAR_ID}/menu/items/local-item?menuVersion=4`, `/api/bars/${BAR_ID}/menu/items/local-item?menuVersion=4`]);
  });

  it("counts a resent edit as done when its new name moved the item to another product (spec 3.14.1)", async () => {
    // Codex review on #199: relinking moves the line to another barMenuItemId, keeping its position.
    let lose = true;
    const api = menuServer([glenfiddich, unlinked], {
      answer: ({ method, body }) => {
        if (method !== "PUT" || !lose) return undefined;
        lose = false;
        // The server renames and relinks the line, and the answer is lost on the way back.
        api.changeElsewhere([
          {
            ...unlinked,
            barMenuItemId: "relinked",
            productId: LAGA_ID,
            productName: "Lagavulin 16 Year Old",
            displayName: body?.displayName as string,
            options: unlinked.options.map((saved) => ({ ...saved, menuEntryOptionId: "relinked-0" })),
          },
          glenfiddich,
        ].map((entry, index) => ({ ...entry, sortOrder: index + 1 })));
        return HttpResponse.error();
      },
    });
    // The edited item is first on the menu.
    api.changeElsewhere([{ ...unlinked, sortOrder: 1 }, { ...glenfiddich, sortOrder: 2 }]);
    const { router } = await openEdit("local-item");

    await user().clear(screen.getByLabelText("메뉴 이름"));
    await user().type(screen.getByLabelText("메뉴 이름"), "라가불린 16년");
    await save("저장하기");
    expect(await screen.findByText("서버에 연결하지 못했어요. 네트워크를 확인해 주세요.")).toBeInTheDocument();
    await save("저장하기");

    await atMenuList(router);
    expect(api.writes().map((call) => call.path)).toEqual([`/api/bars/${BAR_ID}/menu/items/local-item`, `/api/bars/${BAR_ID}/menu/items/local-item`]);
    expect(screen.queryByText("이미 메뉴판에서 빠진 메뉴예요.")).not.toBeInTheDocument();
  });

  it("goes back to the list when the item is gone (404 MENU_ITEM_NOT_FOUND)", async () => {
    menuServer([glenfiddich, unlinked], {
      answer: ({ method }) =>
        method === "PUT" ? HttpResponse.json({ error: { code: "MENU_ITEM_NOT_FOUND", message: "없음", details: { barMenuItemId: "local-item" }, fieldErrors: [] } }, { status: 404 }) : undefined,
    });
    const { router } = await openEdit("local-item");
    await user().type(screen.getByLabelText("메뉴 이름"), " 2");
    await save("저장하기");

    await atMenuList(router);
    expect(await screen.findByText("이미 메뉴판에서 빠진 메뉴예요.")).toBeInTheDocument();
  });

  it("asks before leaving with changes, and leaves at once without", async () => {
    menuServer([glenfiddich]);
    const { router } = await openEdit("gf-item");

    await user().click(screen.getByRole("button", { name: "뒤로" }));
    await atMenuList(router);

    await user().click(await screen.findByRole("link", { name: "Glenfiddich 12 수정" }));
    await title("메뉴 수정");
    await user().type(screen.getByLabelText("메뉴 이름"), "!");
    await user().click(screen.getByRole("button", { name: "뒤로" }));
    const sheet = await screen.findByRole("dialog", { name: "변경을 취소할까요?" });
    await user().click(within(sheet).getByRole("button", { name: "계속 편집" }));
    expect(screen.getByLabelText("메뉴 이름")).toHaveValue("Glenfiddich 12!");
  });

  it("sends one request while the answer is slow, with the form locked", async () => {
    let answer: (() => void) | null = null;
    const api = menuServer([glenfiddich], {
      answer: async ({ method }) => {
        if (method !== "PUT") return undefined;
        await new Promise<void>((resolve) => (answer = resolve));
        return undefined;
      },
    });
    const { router } = await openEdit("gf-item");

    await save("저장하기");
    await waitFor(() => expect(answer).not.toBeNull());
    expect(screen.getByLabelText("메뉴 이름")).toBeDisabled();
    await user().click(screen.getByRole("button", { name: "저장하기" })).catch(() => undefined);
    answer!();

    await atMenuList(router);
    expect(api.writes()).toHaveLength(1);
  });

  it.each([
    ["403", 403, "FORBIDDEN", "이 매장을 관리할 권한이 없어요."],
    ["500", 500, "INTERNAL_ERROR", "서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요."],
    ["503 TEMPORARY_WRITE_CONFLICT", 503, "TEMPORARY_WRITE_CONFLICT", "서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요."],
  ] as const)("keeps the input and says so on %s", async (_, status, code, message) => {
    const api = menuServer([glenfiddich], { answer: ({ method }) => (method === "PUT" ? HttpResponse.json(errorBody(code), { status }) : undefined) });
    await openEdit("gf-item");
    await user().type(screen.getByLabelText("메뉴 이름"), "!");
    await save("저장하기");

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByLabelText("메뉴 이름")).toHaveValue("Glenfiddich 12!");
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    expect(api.writes()).toHaveLength(1);
  });

  it("goes to the bar list when the bar is gone (404 BAR_NOT_FOUND)", async () => {
    menuServer([glenfiddich], { answer: ({ method }) => (method === "PUT" ? HttpResponse.json(errorBody("BAR_NOT_FOUND"), { status: 404 }) : undefined) });
    const { router } = await openEdit("gf-item");
    await user().type(screen.getByLabelText("메뉴 이름"), "!");
    await save("저장하기");

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/bars"));
  });

  it("shows an item no longer on the menu", async () => {
    menuServer([glenfiddich]);
    renderOwnerWeb(`/bars/${BAR_ID}/menu/missing`);

    expect(await screen.findByText("메뉴판에 없는 메뉴예요.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "메뉴 목록으로" })).toBeInTheDocument();
  });
});

describe("owner-only access (spec 2.2)", () => {
  const OTHER_BAR_ID = "33333333-3333-4333-8333-333333333333";

  it.each([`/bars/${OTHER_BAR_ID}/menu`, `/bars/${OTHER_BAR_ID}/menu/new`, `/bars/${OTHER_BAR_ID}/menu/gf-item`])(
    "blocks %s, a bar the user does not own, without asking for its menu",
    async (path) => {
      const api = menuServer([glenfiddich]);
      const otherBar: string[] = [];
      server.use(
        http.all(`/api/bars/${OTHER_BAR_ID}/*`, ({ request }) => {
          otherBar.push(`${request.method} ${new URL(request.url).pathname}`);
          return HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 });
        }),
      );
      renderOwnerWeb(path);

      expect(await screen.findByText("이 매장을 관리할 권한이 없어요.")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "처음 화면으로" })).toBeInTheDocument();
      expect(screen.queryByLabelText("메뉴 이름")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "전체 메뉴 초기화" })).not.toBeInTheDocument();
      expect(otherBar).toEqual([]);
      expect(api.calls).toEqual([]);
    },
  );

  it("closes the editor when the owner lost the bar while editing (403)", async () => {
    let owned = true;
    const api = menuServer([glenfiddich], {
      answer: ({ method }) => {
        if (method !== "PUT") return undefined;
        owned = false;
        return HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 });
      },
    });
    server.use(http.get("/api/me/bars", () => HttpResponse.json({ items: owned ? [bar(BAR_ID, "관악 위스키 바")] : [] })));
    await openEdit("gf-item");

    await user().type(screen.getByLabelText("메뉴 이름"), "!");
    await save("저장하기");

    // The bar list read again no longer has the bar, so the access check closes the editor.
    expect(await screen.findByRole("link", { name: "처음 화면으로" })).toBeInTheDocument();
    expect(screen.getByText("이 매장을 관리할 권한이 없어요.")).toBeInTheDocument();
    expect(screen.queryByLabelText("메뉴 이름")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    expect(api.writes()).toHaveLength(1);
  });

  it("closes the menu when the owner lost the bar before resetting it (403)", async () => {
    let owned = true;
    const api = menuServer([glenfiddich], {
      answer: ({ method }) => {
        if (method !== "POST reset") return undefined;
        owned = false;
        return HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 });
      },
    });
    server.use(http.get("/api/me/bars", () => HttpResponse.json({ items: owned ? [bar(BAR_ID, "관악 위스키 바")] : [] })));
    await openMenu();

    await user().click(screen.getByRole("button", { name: "전체 메뉴 초기화" }));
    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "초기화" }));

    expect(await screen.findByRole("link", { name: "처음 화면으로" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "전체 메뉴 초기화" })).not.toBeInTheDocument();
    expect(api.writes()).toHaveLength(1);
  });
});
