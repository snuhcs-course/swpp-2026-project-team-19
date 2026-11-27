import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ME, errorBody, useOwnerApi } from "../test/api";
import { renderOwnerWeb } from "../test/render";
import { server } from "../test/server";
import { emptyDraft, loadDraft, saveDraft, type ApplicationDraft } from "./draft";
import { searchAddress } from "./kakaoAddress";
import { businessVerificationKey } from "./rules";

vi.mock("../images/prepare", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../images/prepare")>()),
  // jsdom has no canvas: a "prepared" photo carries its file name, so uploads can be checked in order.
  prepareImage: vi.fn(async (file: File) => ({
    blob: new Blob([`img-${file.name}`], { type: "image/jpeg" }),
    fileName: file.name.replace(/\.[^.]*$/, "") + ".jpg",
    width: 100,
    height: 100,
  })),
}));
vi.mock("./kakaoAddress", () => ({ searchAddress: vi.fn() }));

const APPLICATION_ID = "cccccccc-cccc-4ccc-8ccc-ccccccccccc1";
const BAR_ID = "22222222-2222-4222-8222-222222222222";
const BUSINESS = { businessNumber: "1234567891", representativeName: "김사장", openingDate: "2020-03-02" };
const photo = (name: string) => new File([name], name, { type: "image/jpeg" });
const user = () => userEvent.setup();
const spaces = (text: string) => text.replace(/\s+/g, " ").trim();
const heading = (text: string) => screen.findByRole("heading", { level: 2, name: (name) => spaces(name) === spaces(text) });
const next = (label = "다음") => screen.getByRole("button", { name: label });

/** A draft that has passed the business check, starting at `step`. */
function seed(step: ApplicationDraft["step"], change: Partial<ApplicationDraft> = {}): ApplicationDraft {
  const draft: ApplicationDraft = {
    ...emptyDraft(),
    ...BUSINESS,
    verification: { key: businessVerificationKey(BUSINESS), result: "matched", retryAfter: null },
    proposedBarName: "신림 몰트 하우스",
    address: "서울특별시 관악구 신림로 2",
    addressDetail: "3층",
    storePhone: "0212345678",
    contactPhone: "01012345678",
    ...change,
    step,
  };
  saveDraft(ME.userId, draft);
  return draft;
}

/** The API calls of a submission, recorded. */
function submissionApi(overrides: { menus?: () => Response } = {}) {
  const calls: { method: string; path: string; body?: unknown; files?: string[] }[] = [];
  server.use(
    http.post("/api/owner-applications", async ({ request }) => {
      calls.push({ method: "POST", path: "applications", body: await request.json() });
      return HttpResponse.json({ applicationId: APPLICATION_ID, status: "pending" }, { status: 201 });
    }),
    http.put("/api/owner-applications/:id/cover-photo", async ({ request, params }) => {
      const form = await request.formData();
      calls.push({ method: "PUT", path: `cover:${params.id}`, files: await Promise.all(form.getAll("image").map((file) => (file as File).text())) });
      return HttpResponse.json({ applicationId: APPLICATION_ID });
    }),
    http.put("/api/owner-applications/:id/menu-photos", async ({ request, params }) => {
      const form = await request.formData();
      calls.push({ method: "PUT", path: `menus:${params.id}`, files: await Promise.all(form.getAll("images").map((file) => (file as File).text())) });
      return overrides.menus?.() ?? HttpResponse.json({ applicationId: APPLICATION_ID });
    }),
  );
  return calls;
}

function barNames(items: { barId: string; name: string; address: string; hasOwner: boolean }[]) {
  server.use(
    http.get("/api/search/bar-names", () =>
      HttpResponse.json({ items: items.map((item) => ({ ...item, latitude: 37.5, longitude: 127, coverThumbnailUrl: null })), truncated: false }),
    ),
  );
}

beforeEach(() => {
  useOwnerApi();
});

describe("business check (spec 3.11.16)", () => {
  it("goes through manual entry, checks exactly the values typed, and moves on when they match", async () => {
    let sent: unknown;
    server.use(
      http.post("/api/owner-applications/business-verification", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ result: "matched" });
      }),
    );
    const u = user();
    renderOwnerWeb("/apply");

    await heading("매장 등록은\n이렇게 진행돼요");
    await u.click(next("시작하기"));
    await u.click(await screen.findByRole("button", { name: /직접 입력하기/ }));
    await u.type(await screen.findByLabelText("사업자등록번호"), "1234567891");
    expect(screen.getByLabelText("사업자등록번호")).toHaveValue("123-45-67891");
    await u.click(next());
    await u.type(await screen.findByLabelText("대표자 성명"), "김사장");
    await u.click(next());
    await u.type(await screen.findByLabelText("개업일"), "20200302");
    expect(screen.getByLabelText("개업일")).toHaveValue("2020.03.02");
    await u.click(next());
    await heading("이 정보로\n확인할게요");
    await u.click(next("확인하기"));

    await heading("사업자 정보가\n확인됐어요");
    expect(sent).toEqual({ businessRegistrationNumber: "1234567891", representativeName: "김사장", openingDate: "2020-03-02" });
    await u.click(next());
    await heading("매장 이름을\n알려주세요");
  });

  it("refuses a wrong check digit before asking the server", async () => {
    const u = user();
    renderOwnerWeb("/apply/number");

    await u.type(await screen.findByLabelText("사업자등록번호"), "1234567890");

    expect(screen.getByText("번호를 다시 확인해 주세요. 사업자등록증의 10자리와 같아야 해요.")).toBeInTheDocument();
    expect(next()).toBeDisabled();
  });

  it("drops a result for values changed while it was on its way", async () => {
    let answer: (() => void) | undefined;
    server.use(
      http.post("/api/owner-applications/business-verification", async () => {
        await new Promise<void>((resolve) => {
          answer = resolve;
        });
        return HttpResponse.json({ result: "matched" });
      }),
    );
    seed("check", { verification: null });
    const u = user();
    const { router } = renderOwnerWeb("/apply/check");

    await u.click(await screen.findByRole("button", { name: "확인하기" }));
    await waitFor(() => expect(answer).toBeDefined());
    await u.click(screen.getByRole("button", { name: "개업일 수정" }));
    const date = await screen.findByLabelText("개업일");
    await u.clear(date);
    await u.type(date, "20200303");
    answer?.();

    await waitFor(() => expect(loadDraft(ME.userId)?.openingDate).toBe("2020-03-03"));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(router.state.location.pathname).toBe("/owner/apply/opening-date");
    expect(loadDraft(ME.userId)?.verification).toBeNull();
  });

  it("stays where the owner went when a result comes after they left the check", async () => {
    let answer: (() => void) | undefined;
    let answered = false;
    server.use(
      http.post("/api/owner-applications/business-verification", async () => {
        await new Promise<void>((resolve) => (answer = resolve));
        answered = true;
        return HttpResponse.json({ result: "matched" });
      }),
    );
    seed("check", { verification: null });
    const u = user();
    const { router } = renderOwnerWeb("/apply/check");

    await u.click(await screen.findByRole("button", { name: "확인하기" }));
    await waitFor(() => expect(answer).toBeDefined());
    await u.click(screen.getByRole("button", { name: "뒤로" }));
    await heading("개업일을\n알려주세요");
    answer?.();
    await waitFor(() => expect(answered).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(router.state.location.pathname).toBe("/owner/apply/opening-date");
    expect(loadDraft(ME.userId)?.verification).toBeNull();
  });

  it("explains a mismatch and returns to the values to correct them", async () => {
    server.use(http.post("/api/owner-applications/business-verification", () => HttpResponse.json({ result: "not_matched" })));
    seed("check", { verification: null });
    const u = user();
    renderOwnerWeb("/apply/check");

    await u.click(await screen.findByRole("button", { name: "확인하기" }));
    await heading("사업자 정보가\n맞지 않아요");
    await u.click(next("다시 확인하기"));

    await heading("이 정보로\n확인할게요");
  });

  it("lets the owner continue when the NTS check is unavailable", async () => {
    server.use(http.post("/api/owner-applications/business-verification", () => HttpResponse.json({ result: "unavailable" })));
    seed("check", { verification: null });
    const u = user();
    renderOwnerWeb("/apply/check");

    await u.click(await screen.findByRole("button", { name: "확인하기" }));
    await heading("지금은 국세청 확인이\n어려워요");
    await u.click(next("계속하기"));

    await heading("매장 이름을\n알려주세요");
  });

  it("shows when the daily limit resets, in Seoul time", async () => {
    server.use(
      http.post("/api/owner-applications/business-verification", () =>
        HttpResponse.json(
          { error: { code: "RATE_LIMITED", message: "x", details: { retryAfter: "2026-11-20T15:00:00Z" }, fieldErrors: [] } },
          { status: 429 },
        ),
      ),
    );
    seed("check", { verification: null });
    const u = user();
    renderOwnerWeb("/apply/check");

    await u.click(await screen.findByRole("button", { name: "확인하기" }));

    await heading("오늘 확인 횟수를\n모두 썼어요");
    expect(screen.getByText(/11월 21일 0시부터 다시 진행해 주세요/)).toBeInTheDocument();
  });

  it("does not open the result or the review for values that were not checked", async () => {
    seed("review", { verification: { key: "other|values|2020-01-01", result: "matched", retryAfter: null } });
    const { router } = renderOwnerWeb("/apply/review");

    await heading("이 정보로\n확인할게요");
    expect(router.state.location.pathname).toBe("/owner/apply/check");
  });
});

describe("certificate reading (spec 3.11.12)", () => {
  it("fills the fields from the photo for the owner to check", async () => {
    server.use(
      http.post("/api/owner-applications/business-certificate-ocr", () =>
        HttpResponse.json({
          businessRegistrationNumber: "1234567891",
          representativeName: "김사장",
          openingDate: "2020-03-02",
          businessName: "신림 몰트 하우스",
          address: "서울특별시 관악구 신림로 2 3층",
        }),
      ),
    );
    const u = user();
    renderOwnerWeb("/apply/method");

    await u.upload(await screen.findByLabelText("사업자등록증 사진"), photo("certificate.jpg"));

    await heading("읽은 내용이\n맞는지 확인해 주세요");
    expect(screen.getByText("123-45-67891")).toBeInTheDocument();
    expect(screen.getByText("김사장")).toBeInTheDocument();
    expect(screen.getByText("2020.03.02")).toBeInTheDocument();
    expect(loadDraft(ME.userId)).toMatchObject({ inputMethod: "photo", proposedBarName: "신림 몰트 하우스", address: "서울특별시 관악구 신림로 2 3층" });
  });

  it.each([
    [429, "RATE_LIMITED", "오늘 사진으로 읽기는 5번까지 할 수 있어요."],
    [503, "OCR_UNAVAILABLE", "지금은 사진을 읽을 수 없어요. 직접 입력해 주세요."],
  ])("sends the owner to type the values on %i", async (status, code, message) => {
    server.use(http.post("/api/owner-applications/business-certificate-ocr", () => HttpResponse.json(errorBody(code), { status })));
    const u = user();
    renderOwnerWeb("/apply/method");

    await u.upload(await screen.findByLabelText("사업자등록증 사진"), photo("certificate.jpg"));

    expect(await screen.findByText(new RegExp(message.replace(/[.()]/g, "\\$&")))).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /입력$/ })).toHaveLength(3);
  });

  it("keeps what the owner typed after leaving a slow reading", async () => {
    let answer: (() => void) | undefined;
    let answered = false;
    server.use(
      http.post("/api/owner-applications/business-certificate-ocr", async () => {
        await new Promise<void>((resolve) => (answer = resolve));
        answered = true;
        return HttpResponse.json({ businessRegistrationNumber: "2208162517", representativeName: "OCR", openingDate: "2019-01-01", businessName: "OCR 바", address: null });
      }),
    );
    const u = user();
    const { router } = renderOwnerWeb("/apply/method");
    await u.upload(await screen.findByLabelText("사업자등록증 사진"), photo("certificate.jpg"));
    await heading("사업자등록증을\n읽고 있어요");
    await waitFor(() => expect(answer).toBeDefined());

    await u.click(screen.getByRole("button", { name: "뒤로" }));
    await u.click(await screen.findByRole("button", { name: /직접 입력하기/ }));
    await u.type(await screen.findByRole("textbox"), "1234567891");
    answer?.();
    await waitFor(() => expect(answered).toBe(true));
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(router.state.location.pathname).toBe("/owner/apply/number");
    expect(loadDraft(ME.userId)).toMatchObject({ inputMethod: "manual", businessNumber: "1234567891", representativeName: "", proposedBarName: "" });
  });
});

describe("bar (spec 3.11.11)", () => {
  it("asks about a bar with the same name and claims it as the owner's", async () => {
    barNames([{ barId: BAR_ID, name: "관악 위스키 바", address: "관악로 1", hasOwner: false }]);
    seed("bar-name", { proposedBarName: "" });
    const u = user();
    const { router } = renderOwnerWeb("/apply/bar-name");

    await u.type(await screen.findByLabelText("매장 이름"), "관악 위스키 바");
    const card = await screen.findByRole("region", { name: "관악 위스키 바 확인" });
    expect(next()).toBeDisabled();
    await u.click(within(card).getByRole("button", { name: "우리 매장이에요" }));

    await heading("메뉴판 사진을\n올려 주세요");
    expect(router.state.location.pathname).toBe("/owner/apply/menus");
    expect(loadDraft(ME.userId)).toMatchObject({ kind: "existing_bar", existingBar: { barId: BAR_ID } });
  });

  it("explains that a bar with an owner cannot be claimed, and lets the owner register a new bar", async () => {
    barNames([{ barId: BAR_ID, name: "관악 위스키 바", address: "관악로 1", hasOwner: true }]);
    seed("bar-name", { proposedBarName: "" });
    const u = user();
    renderOwnerWeb("/apply/bar-name");

    await u.type(await screen.findByLabelText("매장 이름"), "관악 위스키 바");
    const card = await screen.findByRole("region", { name: "관악 위스키 바 확인" });
    await u.click(within(card).getByRole("button", { name: "우리 매장이에요" }));

    expect(within(card).getByText("이미 업주가 등록된 매장입니다. 운영자에게 문의해 주세요.")).toBeInTheDocument();
    expect(loadDraft(ME.userId)?.kind).toBe("new_bar");
    await u.click(within(card).getByRole("button", { name: "아니에요" }));
    await heading("매장 사진을\n올려 주세요");
  });

  it("asks about a bar whose name is one character", async () => {
    barNames([{ barId: BAR_ID, name: "취", address: "관악로 1", hasOwner: false }]);
    seed("bar-name", { proposedBarName: "" });
    const u = user();
    renderOwnerWeb("/apply/bar-name");

    await u.type(await screen.findByLabelText("매장 이름"), "취");

    expect(await screen.findByRole("region", { name: "취 확인" })).toBeInTheDocument();
    expect(next()).toBeDisabled();
  });

  it("moves on with a name nobody has, once the search has answered", async () => {
    barNames([{ barId: BAR_ID, name: "신림 몰트 하우스 2호점", address: "신림로 3", hasOwner: false }]);
    seed("bar-name", { proposedBarName: "" });
    const u = user();
    renderOwnerWeb("/apply/bar-name");

    await u.type(await screen.findByLabelText("매장 이름"), "신림 몰트 하우스");
    await waitFor(() => expect(next()).toBeEnabled());
    await u.click(next());

    await heading("매장 사진을\n올려 주세요");
  });

  it("fills the address from the Kakao search, or takes it as typed", async () => {
    vi.mocked(searchAddress).mockResolvedValueOnce([{ address: "서울특별시 관악구 신림로 2", label: "신림 몰트 하우스" }]);
    seed("address", { address: "" , addressDetail: "" });
    const u = user();
    renderOwnerWeb("/apply/address");

    await u.type(await screen.findByLabelText("주소"), "신림로 2");
    await u.click(screen.getByRole("button", { name: "주소 검색" }));
    await u.click(await screen.findByRole("button", { name: /서울특별시 관악구 신림로 2/ }));

    expect(screen.getByLabelText("주소")).toHaveValue("서울특별시 관악구 신림로 2");
    vi.mocked(searchAddress).mockRejectedValueOnce(new Error("주소 검색을 쓸 수 없어요. 주소를 직접 입력해 주세요."));
    await u.click(screen.getByRole("button", { name: "주소 검색" }));
    expect(await screen.findByText("주소 검색을 쓸 수 없어요. 주소를 직접 입력해 주세요.")).toBeInTheDocument();
    expect(next()).toBeEnabled();
  });

  it("goes on without a shop phone", async () => {
    seed("bar-phone", { storePhone: "" });
    const u = user();
    renderOwnerWeb("/apply/bar-phone");

    await u.click(await screen.findByRole("button", { name: "가게 전화가 없어요" }));

    await heading("메뉴판 사진을\n올려 주세요");
  });
});

describe("submission (spec 3.11.2, 3.11.17, 3.11.15)", () => {
  async function pickPhotosAndReview(u: ReturnType<typeof user>, { cover = true }: { cover?: boolean } = {}) {
    if (cover) {
      await u.upload(await screen.findByLabelText("대표 사진"), photo("cover.jpg"));
      await u.click(next());
      await u.click(await screen.findByRole("button", { name: "다음" })); // address
      await u.click(await screen.findByRole("button", { name: "다음" })); // shop phone
    }
    await u.upload(await screen.findByLabelText("메뉴판 사진 추가"), [photo("menu-1.jpg"), photo("menu-2.jpg")]);
    await u.click(next());
    await u.click(await screen.findByRole("button", { name: "다음" })); // contact
    await heading("이렇게\n신청할게요");
  }

  it("sends a new bar's application, then its cover photo and menu photos in order", async () => {
    const calls = submissionApi();
    seed("cover");
    const u = user();
    renderOwnerWeb("/apply/cover");
    await pickPhotosAndReview(u);

    await u.click(next("신청하기"));

    await heading("신청을 마쳤어요");
    expect(calls).toEqual([
      {
        method: "POST",
        path: "applications",
        body: {
          applicationType: "new_bar",
          proposedBar: { name: "신림 몰트 하우스", address: "서울특별시 관악구 신림로 2 3층", phone: "0212345678" },
          businessRegistrationNumber: "1234567891",
          representativeName: "김사장",
          openingDate: "2020-03-02",
          contactPhone: "01012345678",
          // Not ticked: no consent to show the contact phone to customers (spec 3.11.2).
          contactPhonePublic: false,
        },
      },
      { method: "PUT", path: `cover:${APPLICATION_ID}`, files: ["img-cover.jpg"] },
      { method: "PUT", path: `menus:${APPLICATION_ID}`, files: ["img-menu-1.jpg", "img-menu-2.jpg"] },
    ]);
    expect(loadDraft(ME.userId)).toBeNull();
  });

  it("sends an existing bar's claim without a cover photo", async () => {
    const calls = submissionApi();
    seed("menus", { kind: "existing_bar", existingBar: { barId: BAR_ID, name: "관악 위스키 바", address: "관악로 1" }, proposedBarName: "관악 위스키 바" });
    const u = user();
    renderOwnerWeb("/apply/menus");
    await pickPhotosAndReview(u, { cover: false });

    await u.click(next("신청하기"));

    await heading("신청을 마쳤어요");
    expect(calls.map((call) => call.path)).toEqual(["applications", `menus:${APPLICATION_ID}`]);
    expect(calls[0]?.body).toEqual({
      applicationType: "existing_bar",
      barId: BAR_ID,
      businessRegistrationNumber: "1234567891",
      representativeName: "김사장",
      openingDate: "2020-03-02",
      contactPhone: "01012345678",
      contactPhonePublic: false,
    });
  });

  it("asks the consent to show the contact phone, off by default, and sends it when ticked", async () => {
    const calls = submissionApi();
    seed("menus", { kind: "existing_bar", existingBar: { barId: BAR_ID, name: "관악 위스키 바", address: "관악로 1" }, proposedBarName: "관악 위스키 바" });
    const u = user();
    renderOwnerWeb("/apply/menus");
    await u.upload(await screen.findByLabelText("메뉴판 사진 추가"), photo("menu-1.jpg"));
    await u.click(next());

    await heading("연락받을 번호를\n알려주세요");
    const consent = screen.getByRole("checkbox", { name: "매장 번호가 없으면 이 번호를 손님에게 보여 줘요" });
    expect(consent).not.toBeChecked();
    expect(screen.getByText("운영팀만 봐요")).toBeInTheDocument();
    await u.click(consent);
    expect(consent).toBeChecked();
    expect(screen.getByText("손님에게 보여요")).toBeInTheDocument();
    expect(loadDraft(ME.userId)?.contactPhonePublic).toBe(true);
    await u.click(next());

    await heading("이렇게\n신청할게요");
    const contact = screen.getByRole("region", { name: "연락처" });
    expect(within(contact).getByText("손님에게 공개")).toBeInTheDocument();
    expect(within(contact).getByText("매장 번호가 없을 때 보여요")).toBeInTheDocument();
    await u.click(next("신청하기"));

    await heading("신청을 마쳤어요");
    expect(calls[0]?.body).toMatchObject({ contactPhone: "01012345678", contactPhonePublic: true });
  });

  it("shows on the review step that the contact phone stays with the operators without consent", async () => {
    seed("menus", { kind: "existing_bar", existingBar: { barId: BAR_ID, name: "관악 위스키 바", address: "관악로 1" }, proposedBarName: "관악 위스키 바" });
    const u = user();
    renderOwnerWeb("/apply/menus");
    await pickPhotosAndReview(u, { cover: false });

    expect(within(screen.getByRole("region", { name: "연락처" })).getByText("보여 주지 않아요")).toBeInTheDocument();
  });

  it("shows the new application's status after the done screen, not a new form", async () => {
    const calls = submissionApi();
    server.use(
      http.get("/api/me/owner-applications", () =>
        HttpResponse.json({ items: calls.length > 0 ? [{ applicationId: APPLICATION_ID, status: "pending" }] : [] }),
      ),
    );
    seed("menus", { kind: "existing_bar", existingBar: { barId: BAR_ID, name: "관악 위스키 바", address: "관악로 1" }, proposedBarName: "관악 위스키 바" });
    const u = user();
    const { router } = renderOwnerWeb("/");
    await heading("메뉴판 사진을\n올려 주세요");
    await pickPhotosAndReview(u, { cover: false });
    await u.click(next("신청하기"));
    await heading("신청을 마쳤어요");

    await u.click(next("확인"));

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/applications"));
  });

  it("retries only the failed photo upload, never the application", async () => {
    let failures = 1;
    const calls = submissionApi({ menus: () => (failures-- > 0 ? HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 }) : HttpResponse.json({})) });
    seed("cover");
    const u = user();
    renderOwnerWeb("/apply/cover");
    await pickPhotosAndReview(u);

    await u.click(next("신청하기"));
    expect(await screen.findByText(/신청은 접수됐지만 사진을 올리지 못했어요/)).toBeInTheDocument();
    expect(loadDraft(ME.userId)).toMatchObject({ applicationId: APPLICATION_ID, uploaded: { cover: true, menus: false } });
    await u.click(next("신청하기"));

    await heading("신청을 마쳤어요");
    expect(calls.map((call) => call.path)).toEqual(["applications", `cover:${APPLICATION_ID}`, `menus:${APPLICATION_ID}`, `menus:${APPLICATION_ID}`]);
  });

  it("keeps the created application as it is and lets only the photos change", async () => {
    seed("contact", { applicationId: APPLICATION_ID, uploaded: { cover: true, menus: false } });
    renderOwnerWeb("/apply/contact");

    await heading("이렇게\n신청할게요");
    expect(screen.getByText("신청은 접수됐어요. 남은 사진만 올리면 돼요. 신청 내용은 바꿀 수 없어요.")).toBeInTheDocument();
    for (const section of ["사업자 정보", "매장 정보", "연락처"]) {
      expect(screen.queryByRole("button", { name: `${section} 수정` })).not.toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "메뉴판 수정" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /바꾸기/ })).toBeInTheDocument();
  });

  it("sends a cover photo replaced after the first one was sent", async () => {
    const calls = submissionApi();
    seed("review", { applicationId: APPLICATION_ID, uploaded: { cover: true, menus: false } });
    const u = user();
    renderOwnerWeb("/apply/review");

    await u.click(await screen.findByRole("button", { name: /바꾸기/ }));
    await u.upload(await screen.findByLabelText("대표 사진"), photo("cover-2.jpg"));
    await u.click(next());
    await u.click(await screen.findByRole("button", { name: "메뉴판 수정" }));
    await u.upload(await screen.findByLabelText("메뉴판 사진 추가"), photo("menu-1.jpg"));
    await u.click(next());
    await heading("이렇게\n신청할게요");
    await u.click(next("신청하기"));

    await heading("신청을 마쳤어요");
    expect(calls.map((call) => [call.path, call.files])).toEqual([
      [`cover:${APPLICATION_ID}`, ["img-cover-2.jpg"]],
      [`menus:${APPLICATION_ID}`, ["img-menu-1.jpg"]],
    ]);
  });

  it("shows the mismatch result when the server refuses the business details", async () => {
    server.use(http.post("/api/owner-applications", () => HttpResponse.json(errorBody("BUSINESS_VERIFICATION_FAILED"), { status: 422 })));
    seed("menus", { kind: "existing_bar", existingBar: { barId: BAR_ID, name: "관악 위스키 바", address: "관악로 1" }, verification: { key: businessVerificationKey(BUSINESS), result: "unavailable", retryAfter: null } });
    const u = user();
    renderOwnerWeb("/apply/menus");
    await pickPhotosAndReview(u, { cover: false });

    await u.click(next("신청하기"));

    await heading("사업자 정보가\n맞지 않아요");
  });

  it("points to the application in progress instead of overwriting its photos", async () => {
    server.use(
      http.post("/api/owner-applications", () =>
        HttpResponse.json({ error: { code: "OWNER_APPLICATION_EXISTS", message: "x", details: { applicationId: "other" }, fieldErrors: [] } }, { status: 409 }),
      ),
    );
    seed("menus", { kind: "existing_bar", existingBar: { barId: BAR_ID, name: "관악 위스키 바", address: "관악로 1" } });
    const u = user();
    renderOwnerWeb("/apply/menus");
    await pickPhotosAndReview(u, { cover: false });

    await u.click(next("신청하기"));

    expect(await screen.findByText("이미 처리 중인 신청이 있어요. 신청 상태를 확인해 주세요.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "신청 상태 보기" })).toBeInTheDocument();
  });

  it("returns to the bar when it already has an owner", async () => {
    server.use(http.post("/api/owner-applications", () => HttpResponse.json(errorBody("BAR_OWNER_EXISTS"), { status: 409 })));
    barNames([]);
    seed("menus", { kind: "existing_bar", existingBar: { barId: BAR_ID, name: "관악 위스키 바", address: "관악로 1" } });
    const u = user();
    renderOwnerWeb("/apply/menus");
    await pickPhotosAndReview(u, { cover: false });

    await u.click(next("신청하기"));

    await heading("매장 이름을\n알려주세요");
    expect(screen.getByRole("alert")).toHaveTextContent("이미 업주가 등록된 매장입니다. 운영자에게 문의해 주세요.");
  });
});

describe("draft", () => {
  it("continues where the owner stopped, and asks for the photos again", async () => {
    seed("review");
    renderOwnerWeb("/apply");

    await heading("이렇게\n신청할게요");
    expect(screen.getByText("새로고침하면 고른 사진이 지워져요. 사진을 다시 골라 주세요.")).toBeInTheDocument();
    expect(next("신청하기")).toBeDisabled();
  });

  it("goes back one step on the path after resuming, not out of the form", async () => {
    seed("contact");
    const u = user();
    renderOwnerWeb("/apply");
    await heading("연락받을 번호를\n알려주세요");

    await u.click(screen.getByRole("button", { name: "뒤로" }));

    await heading("메뉴판 사진을\n올려 주세요");
  });

  it("takes the owner from the start back to an application whose photos were not sent", async () => {
    useOwnerApi({ applications: [{ applicationId: APPLICATION_ID, status: "pending" } as never] });
    seed("review", { applicationId: APPLICATION_ID, uploaded: { cover: true, menus: false } });
    const { router } = renderOwnerWeb("/");

    await heading("이렇게\n신청할게요");
    expect(router.state.location.pathname).toBe("/owner/apply/review");
  });

  it("shows the status of an application sent elsewhere", async () => {
    useOwnerApi({ applications: [{ applicationId: APPLICATION_ID, status: "pending" } as never] });
    seed("contact");
    const { router } = renderOwnerWeb("/");

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/applications"));
  });

  it("is removed when the owner signs out", async () => {
    seed("contact");
    const u = user();
    renderOwnerWeb("/apply/contact");

    await u.click(await screen.findByRole("button", { name: "로그아웃" }));

    await screen.findByRole("button", { name: "Google로 로그인" });
    expect(loadDraft(ME.userId)).toBeNull();
  });
});
