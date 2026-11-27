import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { bar, errorBody, useOwnerApi } from "../test/api";
import { renderOwnerWeb } from "../test/render";
import { server } from "../test/server";
import type { BarDetail } from "./barInfo";

const BAR_ID = "22222222-2222-4222-8222-222222222222";
const OTHER_BAR_ID = "33333333-3333-4333-8333-333333333333";
const user = () => userEvent.setup();
const title = (name: string) => screen.findByRole("heading", { level: 1, name });
const save = () => screen.getByRole("button", { name: "저장하기" });

/**
 * The owner's one bar on a server that keeps PATCH /api/bars/{barId} (spec 3.7): only the fields sent
 * change, trimmed, and a blank description or phone becomes null, as the backend does. The phone customers
 * see (3.6 `customerPhone`) follows as the backend computes it: the bar's phone, else the owner's contact
 * phone when `initial` gives one as `owner_contact`.
 */
function barServer(initial: Partial<BarDetail> = {}, answer?: (body: Record<string, unknown>) => Response | undefined | Promise<Response | undefined>) {
  const ownerContact = initial.customerPhoneSource === "owner_contact" ? (initial.customerPhone ?? null) : null;
  const seen = (detail: BarDetail): BarDetail => {
    const [customerPhone, customerPhoneSource] = detail.phone
      ? [detail.phone, "bar" as const]
      : ownerContact
        ? [ownerContact, "owner_contact" as const]
        : [null, null];
    return { ...detail, customerPhone, customerPhoneSource };
  };
  let current = seen(
    bar(BAR_ID, "관악 위스키 바", {
      description: "싱글몰트 위주의 조용한 바",
      phone: "02-555-1234",
      defaultPourMl: 30,
      tags: ["싱글몰트"],
      ...initial,
    }),
  );
  const patches: Record<string, unknown>[] = [];
  const reads = { bar: 0, myBars: 0 };
  useOwnerApi();
  server.use(
    http.get("/api/me/bars", () => {
      reads.myBars++;
      return HttpResponse.json({ items: [current] });
    }),
    http.get("/api/bars/:barId", () => {
      reads.bar++;
      return HttpResponse.json(current);
    }),
    http.patch("/api/bars/:barId", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      patches.push(body);
      const custom = await answer?.(body);
      if (custom) return custom;
      const clean = (value: unknown) => (typeof value === "string" ? value.trim() || null : value);
      const next = { ...current };
      for (const [key, value] of Object.entries(body)) {
        (next as Record<string, unknown>)[key] = Array.isArray(value) ? value.map((tag: string) => tag.trim()) : clean(value);
      }
      current = seen({ ...next, updatedAt: "2026-11-22T03:00:00Z" });
      return HttpResponse.json(current);
    }),
  );
  return { patches, reads, current: () => current };
}

async function openForm() {
  const view = renderOwnerWeb(`/bars/${BAR_ID}/info`);
  await title("매장 정보 관리");
  await screen.findByRole("button", { name: "저장하기" });
  return view;
}

describe("bar home (/bars/:barId, spec 3.6)", () => {
  it("shows the bar and opens the info editor", async () => {
    barServer();
    const { router } = renderOwnerWeb(`/bars/${BAR_ID}`);

    await title("관악 위스키 바");
    const info = await screen.findByRole("link", { name: /매장 정보 관리/ });
    // The app's fixed line, with commas instead of middle dots.
    expect(info).toHaveTextContent("사진, 소개, 영업시간");
    expect(screen.getByRole("region", { name: "영업 상태" })).toHaveTextContent("영업 상태 변경");
    // OwnerManagementHomeScreen.kt: the menu's item count and last update, with a comma for the middle dot.
    expect(await screen.findByRole("link", { name: /메뉴 관리/ })).toHaveTextContent("게시된 메뉴 0개, 최근 갱신 없음");

    await user().click(info);

    await title("매장 정보 관리");
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/info`);
  });

  it("shows loading while the bar is slow to arrive", async () => {
    let answer: (() => void) | null = null;
    barServer();
    server.use(
      http.get("/api/bars/:barId", async () => {
        await new Promise<void>((resolve) => (answer = resolve));
        return HttpResponse.json(bar(BAR_ID, "관악 위스키 바"));
      }),
    );
    renderOwnerWeb(`/bars/${BAR_ID}`);

    expect(await screen.findByText("매장 정보를 불러오고 있어요.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /매장 정보 관리/ })).not.toBeInTheDocument();

    // Answer only once the request has reached the server.
    await waitFor(() => expect(answer).not.toBeNull());
    answer!();

    expect(await screen.findByRole("link", { name: /매장 정보 관리/ })).toBeInTheDocument();
  });

  it("shows an error with retry, and the bar after retrying", async () => {
    let failures = 1;
    barServer();
    server.use(
      http.get("/api/bars/:barId", () =>
        failures-- > 0
          ? HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 })
          : HttpResponse.json(bar(BAR_ID, "관악 위스키 바")),
      ),
    );
    renderOwnerWeb(`/bars/${BAR_ID}`);

    await user().click(await screen.findByRole("button", { name: "다시 시도" }));

    expect(await screen.findByRole("link", { name: /매장 정보 관리/ })).toBeInTheDocument();
  });

  it("offers no retry when the server answers 403", async () => {
    barServer();
    server.use(http.get("/api/bars/:barId", () => HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 })));
    renderOwnerWeb(`/bars/${BAR_ID}`);

    expect(await screen.findByText("이 화면을 볼 권한이 없어요.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
  });

  it("offers the bar list when the bar is gone (404)", async () => {
    barServer();
    server.use(http.get("/api/bars/:barId", () => HttpResponse.json(errorBody("BAR_NOT_FOUND"), { status: 404 })));
    renderOwnerWeb(`/bars/${BAR_ID}`);

    expect(await screen.findByText("매장을 찾을 수 없어요.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "내 매장 목록으로" })).toHaveAttribute("href", "/owner/bars");
  });
});

describe("bar info editor (/bars/:barId/info, spec 3.7)", () => {
  it("shows the bar's values, with name and address read-only", async () => {
    barServer();
    await openForm();

    expect(screen.getByLabelText("한 줄 소개")).toHaveValue("싱글몰트 위주의 조용한 바");
    expect(screen.getByLabelText("매장 기본 잔 용량 (ml)")).toHaveValue("30");
    expect(screen.getByLabelText("전화번호")).toHaveValue("02-555-1234");
    expect(screen.getByRole("list", { name: "선택한 태그" })).toHaveTextContent("싱글몰트 ×");
    const basics = screen.getByRole("region", { name: "기본 정보" });
    expect(basics).toHaveTextContent("매장명관악 위스키 바");
    expect(basics).toHaveTextContent("주소서울특별시 관악구 관악로 1");
    expect(within(basics).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("changes nothing on the server until saved, then sends only the edited field and shows the saved value", async () => {
    // From OwnerBarEditorComposeTest.kt editingNameChangesOnlyAfterExplicitSave (the description stands in
    // for the name, which the web does not edit).
    const api = barServer();
    const { router } = await openForm();
    const description = screen.getByLabelText("한 줄 소개");

    await user().clear(description);
    await user().type(description, "  위스키 300종  ");
    expect(api.patches).toEqual([]);
    expect(api.current().description).toBe("싱글몰트 위주의 조용한 바");
    const reads = { ...api.reads };

    await user().click(save());

    await title("관악 위스키 바");
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}`);
    expect(api.patches).toEqual([{ description: "위스키 300종" }]);
    // Both the bar and the owner's bar list are read again.
    await waitFor(() => expect(api.reads.bar).toBeGreaterThan(reads.bar));
    expect(api.reads.myBars).toBeGreaterThan(reads.myBars);

    // The editor opens with what the server saved (trimmed), not what was typed.
    await user().click(screen.getByRole("link", { name: /매장 정보 관리/ }));
    expect(await screen.findByLabelText("한 줄 소개")).toHaveValue("위스키 300종");
  });

  it("says that customers see the bar's phone", async () => {
    barServer();
    await openForm();

    expect(screen.getByLabelText("전화번호")).toHaveAccessibleDescription("손님에게 이 번호가 보여요.");
  });

  it("says which contact phone customers see while the bar has none, without putting it in the field", async () => {
    // Spec 3.6 customerPhone: the owner agreed to show their contact phone when applying (3.11.2).
    const api = barServer({ phone: null, customerPhone: "01012345678", customerPhoneSource: "owner_contact" });
    await openForm();

    const phone = screen.getByLabelText("전화번호");
    expect(phone).toHaveValue("");
    expect(phone).toHaveAccessibleDescription(
      "매장 번호가 없어서 손님에게는 사장님 연락처(010-1234-5678)가 보여요. 매장 번호를 입력하면 매장 번호가 대신 보여요.",
    );

    // A bar phone the owner enters comes first (spec 3.9).
    await user().type(phone, "02-777-8888");
    await user().click(save());

    await title("관악 위스키 바");
    expect(api.patches).toEqual([{ phone: "02-777-8888" }]);
    expect(api.current().customerPhoneSource).toBe("bar");
    await user().click(screen.getByRole("link", { name: /매장 정보 관리/ }));
    expect(await screen.findByLabelText("전화번호")).toHaveAccessibleDescription("손님에게 이 번호가 보여요.");
  });

  it("says that customers see no phone without a bar phone or consent", async () => {
    barServer({ phone: null });
    await openForm();

    expect(screen.getByLabelText("전화번호")).toHaveAccessibleDescription("손님에게 보이는 번호가 없어요.");
  });

  it("removes the phone, description and pour when cleared", async () => {
    const api = barServer();
    await openForm();

    await user().clear(screen.getByLabelText("한 줄 소개"));
    await user().clear(screen.getByLabelText("전화번호"));
    await user().clear(screen.getByLabelText("매장 기본 잔 용량 (ml)"));
    await user().click(save());

    await title("관악 위스키 바");
    expect(api.patches).toEqual([{ description: null, phone: null, defaultPourMl: null }]);
  });

  it("returns without a request when nothing changed", async () => {
    const api = barServer();
    const { router } = await openForm();

    await user().click(save());

    await waitFor(() => expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}`));
    expect(api.patches).toEqual([]);
  });

  it("adds, creates and removes tags in the form, and saves the whole list", async () => {
    // From OwnerBarEditorComposeTest.kt inlineTagSelectionOnlyReachesCustomerAfterFormSave.
    const api = barServer();
    await openForm();

    await user().type(screen.getByLabelText("태그 검색"), "혼술");
    await user().click(screen.getByRole("button", { name: "혼술바 추가" }));
    await user().type(screen.getByLabelText("태그 검색"), "  루프탑 ");
    await user().click(screen.getByRole("button", { name: "“루프탑” 새 태그 등록 ＋" }));
    await user().click(screen.getByRole("button", { name: "싱글몰트 빼기" }));

    expect(screen.getByRole("list", { name: "선택한 태그" })).toHaveTextContent("혼술바 ×루프탑 ×");
    expect(screen.getByText("2/5")).toBeInTheDocument();
    expect(api.patches).toEqual([]);

    await user().click(save());

    await title("관악 위스키 바");
    expect(api.patches).toEqual([{ tags: ["혼술바", "루프탑"] }]);
  });

  it("adds a typed tag with Enter instead of saving", async () => {
    const api = barServer();
    await openForm();

    await user().type(screen.getByLabelText("태그 검색"), "루프탑{Enter}");

    expect(screen.getByRole("list", { name: "선택한 태그" })).toHaveTextContent("루프탑 ×");
    expect(api.patches).toEqual([]);
  });

  it("stops at five tags", async () => {
    barServer({ tags: ["가", "나", "다", "라", "마"] });
    await openForm();

    await user().click(screen.getByRole("button", { name: "칵테일 추가" }));

    expect(await screen.findByText("태그는 최대 5개까지 등록할 수 있어요.")).toBeInTheDocument();
    expect(screen.getByText("5/5")).toBeInTheDocument();
  });

  it("keeps saving off while a value is invalid", async () => {
    barServer();
    await openForm();

    await user().clear(screen.getByLabelText("매장 기본 잔 용량 (ml)"));
    await user().type(screen.getByLabelText("매장 기본 잔 용량 (ml)"), "0");

    expect(screen.getByText("기본 잔 용량은 1~999ml 사이로 입력해 주세요.")).toBeInTheDocument();
    expect(save()).toBeDisabled();

    await user().clear(screen.getByLabelText("전화번호"));
    await user().type(screen.getByLabelText("전화번호"), "02-123 내선 4");
    expect(screen.getByText("전화번호는 숫자와 전화번호 기호만 입력해 주세요.")).toBeInTheDocument();
  });

  it("sends one request when pressed again while the answer is slow", async () => {
    let answer = () => {};
    const api = barServer({}, async () => {
      await new Promise<void>((resolve) => (answer = resolve));
      return undefined;
    });
    await openForm();

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    await user().click(save());
    await user().click(save());
    expect(save()).toBeDisabled();

    // Answer only once the request has reached the server.
    await waitFor(() => expect(api.patches).toHaveLength(1));
    answer();

    await title("관악 위스키 바");
    expect(api.patches).toHaveLength(1);
  });

  it("locks the form while saving, so no edit is made that the request would not carry", async () => {
    let answer = () => {};
    const api = barServer({}, async () => {
      await new Promise<void>((resolve) => (answer = resolve));
      return undefined;
    });
    await openForm();

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    await user().click(save());

    expect(screen.getByLabelText("한 줄 소개")).toBeDisabled();
    expect(screen.getByLabelText("전화번호")).toBeDisabled();
    expect(screen.getByLabelText("태그 검색")).toBeDisabled();
    expect(screen.getByRole("button", { name: "싱글몰트 빼기" })).toBeDisabled();

    await waitFor(() => expect(api.patches).toHaveLength(1));
    answer();

    await title("관악 위스키 바");
    expect(api.patches).toEqual([{ description: "싱글몰트 위주의 조용한 바!" }]);
  });

  it("keeps changes made elsewhere when the bar is read again while editing", async () => {
    // The form compares with the bar as it was opened, not with a later refetch (e.g. after a reconnect).
    const api = barServer();
    const { queryClient } = await openForm();

    // Someone else (the app, an operator) changes the phone and the tags; then the bar is read again.
    const reads = api.reads.bar;
    api.current().phone = "02-999-0000";
    api.current().tags = ["운영자 태그"];
    await queryClient.invalidateQueries({ queryKey: ["bars", BAR_ID] });
    await waitFor(() => expect(api.reads.bar).toBeGreaterThan(reads));

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    await user().click(save());

    await title("관악 위스키 바");
    expect(api.patches).toEqual([{ description: "싱글몰트 위주의 조용한 바!" }]);
    expect(api.current().phone).toBe("02-999-0000");
    expect(api.current().tags).toEqual(["운영자 태그"]);
  });

  it("does not ask to discard after a refetch alone", async () => {
    const api = barServer();
    const { queryClient } = await openForm();

    const reads = api.reads.bar;
    api.current().description = "운영자가 바꾼 소개";
    await queryClient.invalidateQueries({ queryKey: ["bars", BAR_ID] });
    await waitFor(() => expect(api.reads.bar).toBeGreaterThan(reads));
    await user().click(screen.getByRole("button", { name: "뒤로" }));

    await title("관악 위스키 바");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("saves other fields when a stored phone does not fit the app's rule, and checks it once edited", async () => {
    // An operator may store any phone up to 30 characters (spec 3.7); the app's rule applies to new input.
    const api = barServer({ phone: "02-123 내선 4" });
    await openForm();

    expect(screen.queryByText("전화번호는 숫자와 전화번호 기호만 입력해 주세요.")).not.toBeInTheDocument();
    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    expect(save()).toBeEnabled();

    await user().type(screen.getByLabelText("전화번호"), "0");
    expect(screen.getByText("전화번호는 숫자와 전화번호 기호만 입력해 주세요.")).toBeInTheDocument();
    expect(save()).toBeDisabled();

    await user().type(screen.getByLabelText("전화번호"), "{Backspace}");
    await user().click(save());

    await title("관악 위스키 바");
    expect(api.patches).toEqual([{ description: "싱글몰트 위주의 조용한 바!" }]);
  });

  it("keeps the unsaved form when reading the bar again fails, and retries on request", async () => {
    const api = barServer();
    const { queryClient } = await openForm();
    await user().type(screen.getByLabelText("한 줄 소개"), " 쓰는 중");

    let failures = 1;
    server.use(
      http.get("/api/bars/:barId", () =>
        failures-- > 0 ? HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 }) : HttpResponse.json(api.current()),
      ),
    );
    await queryClient.invalidateQueries({ queryKey: ["bars", BAR_ID] });

    expect(await screen.findByText(/최신 정보를 불러오지 못했어요/)).toBeInTheDocument();
    expect(screen.getByLabelText("한 줄 소개")).toHaveValue("싱글몰트 위주의 조용한 바 쓰는 중");

    await user().click(screen.getByRole("button", { name: "다시 시도" }));

    await waitFor(() => expect(screen.queryByText(/최신 정보를 불러오지 못했어요/)).not.toBeInTheDocument());
    expect(screen.getByLabelText("한 줄 소개")).toHaveValue("싱글몰트 위주의 조용한 바 쓰는 중");
  });

  it("keeps the unsaved form when reading the bar list again fails", async () => {
    barServer();
    const { queryClient } = await openForm();
    await user().type(screen.getByLabelText("한 줄 소개"), " 쓰는 중");

    server.use(http.get("/api/me/bars", () => HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 })));
    await queryClient.invalidateQueries({ queryKey: ["me", "bars"] });

    expect(await screen.findByText(/최신 정보를 불러오지 못했어요/)).toBeInTheDocument();
    expect(screen.getByLabelText("한 줄 소개")).toHaveValue("싱글몰트 위주의 조용한 바 쓰는 중");
  });

  it("stays while saving instead of offering to discard what is being saved", async () => {
    let answer = () => {};
    const api = barServer({}, async () => {
      await new Promise<void>((resolve) => (answer = resolve));
      return undefined;
    });
    const { router } = await openForm();

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    await user().click(save());
    await waitFor(() => expect(api.patches).toHaveLength(1));

    await user().click(screen.getByRole("button", { name: "뒤로" }));
    await router.navigate(-1);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/info`);

    answer();

    await title("관악 위스키 바");
    expect(api.current().description).toBe("싱글몰트 위주의 조용한 바!");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("stays on the form, still asking before leaving, when the save fails", async () => {
    barServer({}, () => HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 }));
    await openForm();

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    await user().click(save());
    await screen.findByText("서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요.");
    await user().click(screen.getByRole("button", { name: "뒤로" }));

    expect(await screen.findByRole("dialog", { name: "변경을 취소할까요?" })).toBeInTheDocument();
  });

  it("does not add a tag on the Enter that ends an IME composition", async () => {
    barServer();
    await openForm();
    const search = screen.getByLabelText("태그 검색");

    await user().type(search, "루프탑");
    fireEvent.keyDown(search, { key: "Enter", isComposing: true });
    fireEvent.keyDown(search, { key: "Enter", keyCode: 229 });

    expect(screen.queryByRole("button", { name: "루프탑 빼기" })).not.toBeInTheDocument();
    expect(search).toHaveValue("루프탑");

    // The next Enter, after the composition ended, adds it.
    fireEvent.keyDown(search, { key: "Enter" });

    expect(await screen.findByRole("button", { name: "루프탑 빼기" })).toBeInTheDocument();
    expect(search).toHaveValue("");
  });

  it("shows the screen's frame while loading and when the bar cannot be read", async () => {
    barServer();
    server.use(http.get("/api/bars/:barId", () => HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 })));
    const { router } = renderOwnerWeb(`/bars/${BAR_ID}/info`);

    expect(await screen.findByText("이 화면을 볼 권한이 없어요.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "매장 정보 관리" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "로그아웃" })).toBeInTheDocument();

    await user().click(screen.getByRole("button", { name: "뒤로" }));

    await waitFor(() => expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}`));
  });

  it("shows the server's field errors under their fields (422)", async () => {
    const api = barServer({}, () =>
      HttpResponse.json(
        {
          error: {
            code: "VALIDATION_FAILED",
            message: "입력값",
            details: null,
            fieldErrors: [
              { path: "tags[1]", code: "DUPLICATE_TAG", message: "같은 태그가 이미 있습니다." },
              { path: "description", code: "STRING_TOO_LONG", message: "길어요" },
            ],
          },
        },
        { status: 422 },
      ),
    );
    await openForm();

    await user().type(screen.getByLabelText("태그 검색"), "Malt{Enter}");
    await user().click(save());

    expect(await screen.findByText("같은 태그가 이미 있어요.")).toBeInTheDocument();
    expect(screen.getByText("너무 길어요.")).toBeInTheDocument();
    expect(screen.getByText("입력한 내용을 확인해 주세요.")).toBeInTheDocument();
    expect(api.patches).toHaveLength(1);

    // Editing the description clears its server error.
    await user().type(screen.getByLabelText("한 줄 소개"), ".");
    expect(screen.queryByText("너무 길어요.")).not.toBeInTheDocument();
  });

  it("keeps the edits after a server error, and saves on the next try", async () => {
    let failures = 1;
    const api = barServer({}, () =>
      failures-- > 0 ? HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 }) : undefined,
    );
    await openForm();

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    await user().click(save());

    expect(await screen.findByText("서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")).toBeInTheDocument();
    expect(screen.getByLabelText("한 줄 소개")).toHaveValue("싱글몰트 위주의 조용한 바!");

    await user().click(save());

    await title("관악 위스키 바");
    expect(api.patches).toHaveLength(2);
  });

  it("closes the bar when the owner lost it while editing (403)", async () => {
    let owned = true;
    const api = barServer({}, () => {
      owned = false;
      return HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 });
    });
    server.use(http.get("/api/me/bars", () => HttpResponse.json({ items: owned ? [api.current()] : [] })));
    await openForm();

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    await user().click(save());

    // The bar list read again no longer has the bar, so the access check closes the form.
    expect(await screen.findByRole("link", { name: "처음 화면으로" })).toBeInTheDocument();
    expect(screen.getByText("이 매장을 관리할 권한이 없어요.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "저장하기" })).not.toBeInTheDocument();
  });

  it("goes to the bar list when the bar is gone (404), without asking to discard", async () => {
    barServer({}, () => HttpResponse.json(errorBody("BAR_NOT_FOUND"), { status: 404 }));
    const { router } = await openForm();

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    await user().click(save());

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/bars"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("leaving unsaved edits", () => {
  it("asks before leaving, keeps editing, and leaves only when told to", async () => {
    // From OwnerBarEditorComposeTest.kt unsavedBackShowsConfirmationAndPreservesUntilExplicitDiscard.
    const api = barServer();
    const { router } = await openForm();

    await user().type(screen.getByLabelText("한 줄 소개"), " 임시");
    await user().click(screen.getByRole("button", { name: "뒤로" }));

    const sheet = await screen.findByRole("dialog", { name: "변경을 취소할까요?" });
    expect(within(sheet).getByText("저장하지 않은 수정 사항은 사라집니다.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/info`);

    await user().click(within(sheet).getByRole("button", { name: "계속 편집" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByLabelText("한 줄 소개")).toHaveValue("싱글몰트 위주의 조용한 바 임시");

    await user().click(screen.getByRole("button", { name: "뒤로" }));
    await user().click(within(await screen.findByRole("dialog")).getByRole("button", { name: "변경 취소" }));

    await title("관악 위스키 바");
    expect(api.patches).toEqual([]);
    expect(api.current().description).toBe("싱글몰트 위주의 조용한 바");
  });

  it("asks on the browser's back too", async () => {
    barServer();
    const { router } = renderOwnerWeb(`/bars/${BAR_ID}`);
    await user().click(await screen.findByRole("link", { name: /매장 정보 관리/ }));
    await screen.findByRole("button", { name: "저장하기" });

    await user().type(screen.getByLabelText("전화번호"), "9");
    await router.navigate(-1);

    expect(await screen.findByRole("dialog", { name: "변경을 취소할까요?" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/info`);
  });

  it("leaves at once without edits", async () => {
    barServer();
    await openForm();

    await user().click(screen.getByRole("button", { name: "뒤로" }));

    await title("관악 위스키 바");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("asks the browser before closing or reloading the tab, only with edits", async () => {
    barServer();
    await openForm();

    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    const edited = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(edited);
    expect(edited.defaultPrevented).toBe(true);
  });

  it("signs out without asking", async () => {
    barServer();
    const { router } = await openForm();

    await user().type(screen.getByLabelText("한 줄 소개"), "!");
    fireEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    await title("BottleMap 사장님");
    expect(router.state.location.pathname).toBe("/owner/login");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("owner-only access", () => {
  it.each([`/bars/${OTHER_BAR_ID}`, `/bars/${OTHER_BAR_ID}/info`])("blocks %s, a bar the user does not own", async (path) => {
    barServer();
    renderOwnerWeb(path);

    expect(await screen.findByText("이 매장을 관리할 권한이 없어요.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "저장하기" })).not.toBeInTheDocument();
  });
});
