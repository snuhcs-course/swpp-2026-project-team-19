import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { emptyDraft, loadDraft, saveDraft, type ApplicationDraft } from "../application/draft";
import { businessVerificationKey } from "../application/rules";
import { ME, bar, errorBody, ownerApplication, useOwnerApi } from "../test/api";
import { FakeGateway } from "../test/fakeGateway";
import { renderOwnerWeb } from "../test/render";
import { server } from "../test/server";
import { CANCELED_NOTICE, CANCEL_NOT_FOUND_NOTICE, CANCEL_STATE_CHANGED_NOTICE } from "./CancelApplicationSheet";

const BAR_ID = "22222222-2222-4222-8222-222222222222";
const OTHER_BAR_ID = "33333333-3333-4333-8333-333333333333";
const APPLICATION_ID = "cccccccc-cccc-4ccc-8ccc-ccccccccccc1";
const user = () => userEvent.setup();
const title = (name: string) => screen.findByRole("heading", { level: 1, name });
const card = (name: string) => screen.findByRole("article", { name });
const proposed = (name: string) => ({ name, address: "서울특별시 관악구 관악로 1 2층", phone: "025551234" });
const BUSINESS = { businessNumber: "1234567891", representativeName: "김민준", openingDate: "2019-05-14" };
const PUBLISHED = { menuBoardId: "m", menuVersion: 1, publishedAt: "2026-11-20T03:00:00Z", confirmedAt: null };

/** A draft whose application was sent from this browser, as the form leaves it (its business check current). */
function saveSentDraft(applicationId: string, change: Partial<ApplicationDraft> = {}) {
  saveDraft(ME.userId, {
    ...emptyDraft(),
    ...BUSINESS,
    verification: { key: businessVerificationKey(BUSINESS), result: "matched", retryAfter: null },
    step: "review",
    applicationId,
    ...change,
  });
}

/** The cancel API, recording each call; `answer` decides the response. */
function cancelApi(answer: (applicationId: string) => Response | Promise<Response>) {
  const calls: string[] = [];
  server.use(
    http.post("/api/owner-applications/:id/cancel", ({ params }) => {
      calls.push(String(params.id));
      return answer(String(params.id));
    }),
  );
  return calls;
}

describe("application status (/applications)", () => {
  it("shows each application by status, newest first, as the server sends them", async () => {
    useOwnerApi({
      bars: [bar(BAR_ID, "관악 위스키 바")],
      applications: [
        ownerApplication({ proposedBar: proposed("검토 바"), createdAt: "2026-11-20T15:30:00Z" }),
        ownerApplication({
          status: "rejected",
          proposedBar: proposed("거절 바"),
          rejectionReason: "사업자 주소에서 매장을 확인할 수 없었어요.",
          reviewedAt: "2026-11-21T03:00:00Z",
        }),
        ownerApplication({ status: "canceled", proposedBar: proposed("취소 바") }),
        // Managed now: on the bar list, not here.
        ownerApplication({ status: "approved", applicationType: "existing_bar", proposedBar: null, bar: { barId: BAR_ID, name: "관악 위스키 바", address: "주소" } }),
        // Approved, but the ownership was ended (spec 3.11.10).
        ownerApplication({ status: "approved", applicationType: "existing_bar", proposedBar: null, bar: { barId: OTHER_BAR_ID, name: "해제된 바", address: "주소" } }),
      ],
    });
    renderOwnerWeb("/applications");

    const pending = await card("검토 바");
    expect(within(pending).getByText("검토 중")).toBeInTheDocument();
    expect(within(pending).getByText("11월 21일에 신청했어요")).toBeInTheDocument();
    expect(within(pending).getByRole("list", { name: "진행 상황" })).toHaveTextContent("신청 완료운영팀 확인 중승인");
    expect(within(pending).getByRole("link", { name: "신청 내용 보기" })).toBeInTheDocument();
    expect(within(pending).getByRole("button", { name: "신청 취소" })).toBeInTheDocument();
    expect(within(pending).queryByRole("link", { name: "남은 사진 보내기" })).not.toBeInTheDocument();

    const rejected = await card("거절 바");
    expect(within(rejected).getByText("승인되지 않음")).toBeInTheDocument();
    expect(within(rejected).getByText("11월 21일에 검토했어요")).toBeInTheDocument();
    expect(within(rejected).getByText("운영팀이 남긴 이유")).toBeInTheDocument();
    expect(within(rejected).getByText("사업자 주소에서 매장을 확인할 수 없었어요.")).toBeInTheDocument();
    expect(within(rejected).getByRole("button", { name: "다시 신청하기" })).toBeInTheDocument();
    expect(within(rejected).getByRole("button", { name: "목록에서 지우기" })).toBeInTheDocument();

    const canceled = await card("취소 바");
    expect(within(canceled).getByText("취소됨")).toBeInTheDocument();
    expect(within(canceled).getByText("신청이 취소됐어요.")).toBeInTheDocument();
    // As in the app, a canceled application has no reapply: "다른 매장 등록하기" starts a new one.
    expect(within(canceled).queryByRole("button", { name: "다시 신청하기" })).not.toBeInTheDocument();

    const ended = await card("해제된 바");
    expect(within(ended).getByText("승인됨")).toBeInTheDocument();
    expect(within(ended).getByText("지금은 이 매장의 관리 권한이 없어요.")).toBeInTheDocument();
    expect(within(ended).queryByRole("button")).not.toBeInTheDocument();

    expect(screen.queryByRole("article", { name: "관악 위스키 바" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("article").map((item) => item.getAttribute("aria-label"))).toEqual(["검토 바", "거절 바", "취소 바", "해제된 바"]);
    expect(screen.getByRole("link", { name: "내 매장 목록으로" })).toHaveAttribute("href", "/owner/bars");
  });

  it("hides the reason box when a rejection has no reason", async () => {
    useOwnerApi({ applications: [ownerApplication({ status: "rejected", proposedBar: proposed("거절 바"), rejectionReason: null })] });
    renderOwnerWeb("/applications");

    await card("거절 바");
    expect(screen.queryByText("운영팀이 남긴 이유")).not.toBeInTheDocument();
  });

  it("offers to send the photos of an application sent from this browser", async () => {
    useOwnerApi({ applications: [ownerApplication({ applicationId: APPLICATION_ID, proposedBar: proposed("검토 바") })] });
    saveSentDraft(APPLICATION_ID, { uploaded: { cover: true, menus: false } });
    renderOwnerWeb("/applications");

    const pending = await card("검토 바");
    expect(within(pending).getByText("아직 보내지 못한 사진이 있어요.")).toBeInTheDocument();
    expect(within(pending).getByRole("link", { name: "남은 사진 보내기" })).toHaveAttribute("href", "/owner/apply");
  });

  it("starts an application from the empty list", async () => {
    useOwnerApi();
    const { router } = renderOwnerWeb("/applications");

    expect(await screen.findByText("아직 신청한 매장이 없어요")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "내 매장 목록으로" })).not.toBeInTheDocument();
    await user().click(screen.getByRole("button", { name: "매장 등록 신청하기" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/apply/intro"));
  });

  it("shows loading while the list is slow to arrive", async () => {
    let answer = () => {};
    useOwnerApi();
    server.use(
      http.get("/api/me/owner-applications", async () => {
        await new Promise<void>((resolve) => (answer = resolve));
        return HttpResponse.json({ items: [ownerApplication({ proposedBar: proposed("검토 바") })] });
      }),
    );
    renderOwnerWeb("/applications");

    expect(await screen.findByText("신청 상태를 불러오고 있어요.")).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();

    answer();

    await card("검토 바");
  });

  it("shows an error with retry, and the list after retrying", async () => {
    let failures = 1;
    useOwnerApi();
    server.use(
      http.get("/api/me/owner-applications", () =>
        failures-- > 0
          ? HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 })
          : HttpResponse.json({ items: [ownerApplication({ proposedBar: proposed("검토 바") })] }),
      ),
    );
    renderOwnerWeb("/applications");

    await user().click(await screen.findByRole("button", { name: "다시 시도" }));

    await card("검토 바");
  });

  it("offers no retry when the server answers 403", async () => {
    useOwnerApi();
    server.use(http.get("/api/me/owner-applications", () => HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 })));
    renderOwnerWeb("/applications");

    expect(await screen.findByText("이 화면을 볼 권한이 없어요.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
  });
});

describe("cancel (spec 3.11.5)", () => {
  function pendingApi() {
    let status: "pending" | "canceled" | "approved" = "pending";
    const application = () => ownerApplication({ applicationId: APPLICATION_ID, status, proposedBar: proposed("검토 바") });
    useOwnerApi();
    server.use(
      http.get("/api/me/owner-applications", () => HttpResponse.json({ items: [application()] })),
      http.get("/api/owner-applications/:id", () => HttpResponse.json(application())),
    );
    return { set: (next: typeof status) => (status = next), application };
  }

  async function openSheet() {
    await user().click(within(await card("검토 바")).getByRole("button", { name: "신청 취소" }));
    return screen.getByRole("dialog", { name: "신청을 취소할까요?" });
  }

  it("sends nothing when the owner closes the sheet", async () => {
    pendingApi();
    const calls = cancelApi(() => HttpResponse.json({}));
    renderOwnerWeb("/applications");

    const sheet = await openSheet();
    expect(within(sheet).getByText("취소하면 처음부터 다시 신청해야 해요.")).toBeInTheDocument();
    await user().click(within(sheet).getByRole("button", { name: "닫기" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it("cancels, shows the application canceled, and drops this browser's draft for it", async () => {
    const api = pendingApi();
    saveSentDraft(APPLICATION_ID);
    const calls = cancelApi(() => {
      api.set("canceled");
      return HttpResponse.json(api.application());
    });
    renderOwnerWeb("/applications");

    await user().click(within(await openSheet()).getByRole("button", { name: "취소하기" }));

    expect(await screen.findByText(CANCELED_NOTICE)).toBeInTheDocument();
    expect(within(await card("검토 바")).getByText("취소됨")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls).toEqual([APPLICATION_ID]);
    expect(loadDraft(ME.userId)).toBeNull();
  });

  it("keeps a draft for another application", async () => {
    const api = pendingApi();
    saveSentDraft("dddddddd-dddd-4ddd-8ddd-ddddddddddd1");
    cancelApi(() => {
      api.set("canceled");
      return HttpResponse.json(api.application());
    });
    renderOwnerWeb("/applications");

    await user().click(within(await openSheet()).getByRole("button", { name: "취소하기" }));

    expect(await screen.findByText(CANCELED_NOTICE)).toBeInTheDocument();
    expect(loadDraft(ME.userId)?.applicationId).toBe("dddddddd-dddd-4ddd-8ddd-ddddddddddd1");
  });

  it("reloads the list when the application is gone (404)", async () => {
    pendingApi();
    let listCalls = 0;
    server.use(
      http.get("/api/me/owner-applications", () => {
        listCalls++;
        return HttpResponse.json({ items: listCalls === 1 ? [ownerApplication({ applicationId: APPLICATION_ID, proposedBar: proposed("검토 바") })] : [] });
      }),
    );
    cancelApi(() => HttpResponse.json(errorBody("OWNER_APPLICATION_NOT_FOUND"), { status: 404 }));
    renderOwnerWeb("/applications");

    await user().click(within(await openSheet()).getByRole("button", { name: "취소하기" }));

    expect(await screen.findByText(CANCEL_NOT_FOUND_NOTICE)).toBeInTheDocument();
    expect(await screen.findByText("아직 신청한 매장이 없어요")).toBeInTheDocument();
    expect(listCalls).toBe(2);
  });

  it("shows the new status when the application was approved meanwhile (409)", async () => {
    const api = pendingApi();
    cancelApi(() => {
      api.set("approved");
      return HttpResponse.json(
        { error: { code: "INVALID_APPLICATION_STATE", message: "상태", details: { status: "approved" }, fieldErrors: [] } },
        { status: 409 },
      );
    });
    renderOwnerWeb("/applications");

    await user().click(within(await openSheet()).getByRole("button", { name: "취소하기" }));

    expect(await screen.findByText(CANCEL_STATE_CHANGED_NOTICE)).toBeInTheDocument();
    expect(within(await card("검토 바")).getByText("승인됨")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the sheet open with the message when the server fails, and cancels on the next try", async () => {
    const api = pendingApi();
    let failures = 1;
    const calls = cancelApi(() => {
      if (failures-- > 0) return HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 });
      api.set("canceled");
      return HttpResponse.json(api.application());
    });
    renderOwnerWeb("/applications");

    const sheet = await openSheet();
    await user().click(within(sheet).getByRole("button", { name: "취소하기" }));

    expect(await within(sheet).findByText("서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user().click(within(sheet).getByRole("button", { name: "취소하기" }));

    expect(await screen.findByText(CANCELED_NOTICE)).toBeInTheDocument();
    expect(calls).toHaveLength(2);
  });

  it("sends one request when pressed again while the answer is slow", async () => {
    const api = pendingApi();
    let answer = () => {};
    const calls = cancelApi(async () => {
      await new Promise<void>((resolve) => (answer = resolve));
      api.set("canceled");
      return HttpResponse.json(api.application());
    });
    renderOwnerWeb("/applications");

    const sheet = await openSheet();
    const confirm = within(sheet).getByRole("button", { name: "취소하기" });
    await user().click(confirm);
    await user().click(confirm);
    await user().keyboard("{Escape}");

    expect(confirm).toBeDisabled();
    expect(within(sheet).getByRole("button", { name: "닫기" })).toBeDisabled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    answer();

    expect(await screen.findByText(CANCELED_NOTICE)).toBeInTheDocument();
    expect(calls).toEqual([APPLICATION_ID]);
  });
});

describe("reapply and remove (rejected)", () => {
  it("starts a new-bar application from the rejected one, checked again", async () => {
    useOwnerApi({
      applications: [
        ownerApplication({
          status: "rejected",
          proposedBar: { name: "몰트 앤 무드", address: "서울특별시 관악구 관악로 1 2층", phone: "025551234" },
          rejectionReason: "다시 확인해 주세요.",
        }),
      ],
    });
    // The app saves over a draft in progress; so does the web.
    saveDraft(ME.userId, { ...emptyDraft(), step: "representative", businessNumber: "9999999999" });
    const { router } = renderOwnerWeb("/applications");

    await user().click(within(await card("몰트 앤 무드")).getByRole("button", { name: "다시 신청하기" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/apply/intro"));
    expect(loadDraft(ME.userId)).toMatchObject({
      kind: "new_bar",
      businessNumber: "1234567891",
      representativeName: "김민준",
      openingDate: "2019-05-14",
      proposedBarName: "몰트 앤 무드",
      address: "서울특별시 관악구 관악로 1 2층",
      storePhone: "025551234",
      contactPhone: "01012345678",
      verification: null,
      applicationId: null,
    });

    // The review needs a new business check first.
    await router.navigate("/apply/review");
    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/apply/check"));
  });

  it("starts an existing-bar claim from the rejected one with the same bar", async () => {
    useOwnerApi({
      applications: [
        ownerApplication({
          status: "rejected",
          applicationType: "existing_bar",
          proposedBar: null,
          bar: { barId: BAR_ID, name: "관악 위스키 바", address: "서울특별시 관악구 관악로 2" },
        }),
      ],
    });
    const { router } = renderOwnerWeb("/applications");

    await user().click(within(await card("관악 위스키 바")).getByRole("button", { name: "다시 신청하기" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/apply/intro"));
    expect(loadDraft(ME.userId)).toMatchObject({
      kind: "existing_bar",
      existingBar: { barId: BAR_ID, name: "관악 위스키 바", address: "서울특별시 관악구 관악로 2" },
    });
  });

  it("removes a rejection from the list on this browser, and the start screen then offers to apply", async () => {
    const rejected = ownerApplication({ status: "rejected", proposedBar: proposed("거절 바") });
    useOwnerApi({ applications: [rejected] });
    const first = renderOwnerWeb("/applications");

    await user().click(within(await card("거절 바")).getByRole("button", { name: "목록에서 지우기" }));
    const sheet = screen.getByRole("dialog", { name: "이 신청을 지울까요?" });
    expect(within(sheet).getByText("같은 매장은 언제든 다시 신청할 수 있어요.")).toBeInTheDocument();
    await user().click(within(sheet).getByRole("button", { name: "지우기" }));

    expect(await screen.findByText("아직 신청한 매장이 없어요")).toBeInTheDocument();
    first.unmount();

    // Kept for this account: the start screen no longer sends them to the status.
    const { router } = renderOwnerWeb("/");
    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/apply/intro"));
  });

  it("keeps the card when the owner closes the remove sheet", async () => {
    useOwnerApi({ applications: [ownerApplication({ status: "rejected", proposedBar: proposed("거절 바") })] });
    renderOwnerWeb("/applications");

    await user().click(within(await card("거절 바")).getByRole("button", { name: "목록에서 지우기" }));
    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "닫기" }));

    expect(await card("거절 바")).toBeInTheDocument();
  });
});

describe("another application (다른 매장 등록하기)", () => {
  it("continues a draft in progress", async () => {
    useOwnerApi({ applications: [ownerApplication({ proposedBar: proposed("검토 바") })] });
    saveDraft(ME.userId, { ...emptyDraft(), step: "representative", businessNumber: "1234567891" });
    const { router } = renderOwnerWeb("/applications");

    await card("검토 바");
    await user().click(screen.getByRole("button", { name: "다른 매장 등록하기" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/apply/representative"));
  });

  it("starts anew instead of reopening an application that was canceled", async () => {
    useOwnerApi({ applications: [ownerApplication({ applicationId: APPLICATION_ID, status: "canceled", proposedBar: proposed("취소 바") })] });
    saveSentDraft(APPLICATION_ID);
    const { router } = renderOwnerWeb("/applications");

    await card("취소 바");
    await user().click(screen.getByRole("button", { name: "다른 매장 등록하기" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/apply/intro"));
    expect(loadDraft(ME.userId)?.applicationId ?? null).toBeNull();
  });
});

describe("application details (/applications/:id, spec 3.11.4)", () => {
  it("shows a pending new-bar application read-only, with photo counts", async () => {
    useOwnerApi();
    server.use(
      http.get("/api/owner-applications/:id", () =>
        HttpResponse.json(
          ownerApplication({
            applicationId: APPLICATION_ID,
            coverPhoto: { imageUrl: "https://x/c.jpg", thumbnailUrl: "https://x/t.jpg", imageUrlExpiresAt: null },
            menuPhotos: [
              { imageOrder: 1, imageUrl: "https://x/1.jpg", imageUrlExpiresAt: null },
              { imageOrder: 2, imageUrl: "https://x/2.jpg", imageUrlExpiresAt: null },
            ],
          }),
        ),
      ),
    );
    renderOwnerWeb(`/applications/${APPLICATION_ID}`);

    await title("신청한 내용");
    expect(await screen.findByText("검토 중에는 내용을 수정할 수 없어요.")).toBeInTheDocument();
    const business = screen.getByRole("region", { name: "사업자 정보" });
    expect(business).toHaveTextContent("등록번호123-45-67891");
    expect(business).toHaveTextContent("대표자김민준");
    expect(business).toHaveTextContent("개업일2019.05.14");
    const barInfo = screen.getByRole("region", { name: "매장 정보" });
    expect(barInfo).toHaveTextContent("이름몰트 앤 무드");
    expect(barInfo).toHaveTextContent("대표 사진1장");
    expect(barInfo).toHaveTextContent("주소서울특별시 관악구 관악로 1 2층");
    expect(barInfo).toHaveTextContent("매장 전화02-555-1234");
    expect(screen.getByRole("region", { name: "메뉴판" })).toHaveTextContent("메뉴판 사진2장");
    expect(screen.getByRole("region", { name: "연락처" })).toHaveTextContent("010-1234-5678");
    // Counts only, as in the app.
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /수정/ })).not.toBeInTheDocument();
  });

  it("shows only the bar name of an existing-bar claim", async () => {
    useOwnerApi();
    server.use(
      http.get("/api/owner-applications/:id", () =>
        HttpResponse.json(
          ownerApplication({
            applicationId: APPLICATION_ID,
            applicationType: "existing_bar",
            proposedBar: null,
            bar: { barId: BAR_ID, name: "관악 위스키 바", address: "주소" },
          }),
        ),
      ),
    );
    renderOwnerWeb(`/applications/${APPLICATION_ID}`);

    const barInfo = await screen.findByRole("region", { name: "매장 정보" });
    expect(barInfo).toHaveTextContent("이름관악 위스키 바");
    expect(barInfo).not.toHaveTextContent("주소");
    expect(screen.getByRole("region", { name: "메뉴판" })).toHaveTextContent("메뉴판 사진없음");
  });

  it("cancels from the details and shows it canceled", async () => {
    let status: "pending" | "canceled" = "pending";
    const application = () => ownerApplication({ applicationId: APPLICATION_ID, status });
    useOwnerApi({ applications: [application()] });
    server.use(http.get("/api/owner-applications/:id", () => HttpResponse.json(application())));
    cancelApi(() => {
      status = "canceled";
      return HttpResponse.json(application());
    });
    renderOwnerWeb(`/applications/${APPLICATION_ID}`);

    await user().click(await screen.findByRole("button", { name: "신청 취소" }));
    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "취소하기" }));

    expect(await screen.findByText(CANCELED_NOTICE)).toBeInTheDocument();
    expect(screen.getByText("취소됨")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "신청 취소" })).not.toBeInTheDocument();
  });

  it("does not show someone else's application, and offers no retry (404)", async () => {
    useOwnerApi();
    server.use(
      http.get("/api/owner-applications/:id", () => HttpResponse.json(errorBody("OWNER_APPLICATION_NOT_FOUND"), { status: 404 })),
    );
    renderOwnerWeb(`/applications/${APPLICATION_ID}`);

    expect(await screen.findByText("신청을 찾지 못했어요.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "신청 목록으로" })).toHaveAttribute("href", "/owner/applications");
  });

  it("offers retry after a server error", async () => {
    let failures = 1;
    useOwnerApi();
    server.use(
      http.get("/api/owner-applications/:id", () =>
        failures-- > 0
          ? HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 })
          : HttpResponse.json(ownerApplication({ applicationId: APPLICATION_ID })),
      ),
    );
    renderOwnerWeb(`/applications/${APPLICATION_ID}`);

    await user().click(await screen.findByRole("button", { name: "다시 시도" }));

    expect(await screen.findByRole("region", { name: "사업자 정보" })).toBeInTheDocument();
  });
});

describe("my bars (/bars, spec 3.11.9)", () => {
  it("lists the managed bars and opens the chosen one", async () => {
    useOwnerApi({
      bars: [
        bar(BAR_ID, "관악 위스키 바", { address: "서울특별시 관악구 관악로 1", currentMenu: PUBLISHED }),
        bar(OTHER_BAR_ID, "신림 몰트 하우스", { address: "서울특별시 관악구 신림로 2" }),
      ],
    });
    const { router } = renderOwnerWeb("/bars");

    const published = await card("관악 위스키 바");
    expect(within(published).getByText("승인됨")).toBeInTheDocument();
    expect(within(published).getByText("서울특별시 관악구 관악로 1")).toBeInTheDocument();
    const fresh = await card("신림 몰트 하우스");
    expect(within(fresh).getByText("메뉴 확인 필요")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /신청 현황/ })).not.toBeInTheDocument();

    await user().click(within(fresh).getByRole("link", { name: "매장 관리하기" }));

    await title("신림 몰트 하우스");
    expect(router.state.location.pathname).toBe(`/owner/bars/${OTHER_BAR_ID}`);
  });

  it("links to the applications that are still open", async () => {
    useOwnerApi({
      bars: [bar(BAR_ID, "관악 위스키 바")],
      applications: [
        ownerApplication(),
        ownerApplication({ status: "rejected" }),
        ownerApplication({ status: "canceled" }),
        ownerApplication({ status: "approved", bar: { barId: BAR_ID, name: "관악 위스키 바", address: "주소" } }),
      ],
    });
    renderOwnerWeb("/bars");

    expect(await screen.findByRole("link", { name: "신청 현황 2건" })).toHaveAttribute("href", "/owner/applications");
  });

  it("sends an owner without bars to their applications", async () => {
    useOwnerApi({ applications: [ownerApplication()] });
    renderOwnerWeb("/bars");

    expect(await screen.findByText("아직 관리하는 매장이 없어요")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "신청 현황 보기" })).toHaveAttribute("href", "/owner/applications");
  });

  it("offers to apply when there is neither a bar nor an application", async () => {
    useOwnerApi();
    const { router } = renderOwnerWeb("/bars");

    await user().click(await screen.findByRole("button", { name: "매장 등록 신청하기" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/apply/intro"));
  });

  it("shows an error with retry, and the bars after retrying", async () => {
    let failures = 1;
    useOwnerApi();
    server.use(
      http.get("/api/me/bars", () =>
        failures-- > 0
          ? HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 })
          : HttpResponse.json({ items: [bar(BAR_ID, "관악 위스키 바")] }),
      ),
    );
    renderOwnerWeb("/bars");

    await user().click(await screen.findByRole("button", { name: "다시 시도" }));

    await card("관악 위스키 바");
  });

  it("shows the bars even when the applications fail to load", async () => {
    useOwnerApi({ bars: [bar(BAR_ID, "관악 위스키 바")] });
    server.use(http.get("/api/me/owner-applications", () => HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 })));
    renderOwnerWeb("/bars");

    await card("관악 위스키 바");
    expect(screen.queryByRole("link", { name: /신청 현황/ })).not.toBeInTheDocument();
  });
});

describe("authorization before and after approval", () => {
  it.each(["/applications", `/applications/${APPLICATION_ID}`, "/bars"])("sends a signed-out visitor of %s to sign-in", async (path) => {
    const gateway = new FakeGateway({ signedIn: false });
    const { router } = renderOwnerWeb(path, { gateway });

    await title("BottleMap 사장님");
    expect(router.state.location.pathname).toBe("/owner/login");
    await user().click(screen.getByRole("button", { name: "Google로 로그인" }));
    expect(sessionStorage.getItem("bottlemap-owner-web-return-path")).toBe(path);
  });

  it("before approval: the start screen shows the application, and the bar stays closed", async () => {
    useOwnerApi({ applications: [ownerApplication({ applicationType: "existing_bar", proposedBar: null, bar: { barId: BAR_ID, name: "관악 위스키 바", address: "주소" } })] });
    const { router } = renderOwnerWeb("/");

    await title("등록 신청 상태");
    expect(router.state.location.pathname).toBe("/owner/applications");
    expect(await card("관악 위스키 바")).toHaveTextContent("검토 중");

    await router.navigate(`/bars/${BAR_ID}`);
    expect(await screen.findByText("이 매장을 관리할 권한이 없어요.")).toBeInTheDocument();
  });

  it("after approval: the start screen shows the bar, which opens", async () => {
    useOwnerApi({
      bars: [bar(BAR_ID, "관악 위스키 바")],
      applications: [ownerApplication({ status: "approved", applicationType: "existing_bar", proposedBar: null, bar: { barId: BAR_ID, name: "관악 위스키 바", address: "주소" } })],
    });
    const { router } = renderOwnerWeb("/");

    await title("내 매장");
    expect(router.state.location.pathname).toBe("/owner/bars");
    await user().click(within(await card("관악 위스키 바")).getByRole("link", { name: "매장 관리하기" }));

    await title("관악 위스키 바");
  });

  it("after the ownership ends: the bar closes and the approval shows no management", async () => {
    useOwnerApi({
      applications: [ownerApplication({ status: "approved", applicationType: "existing_bar", proposedBar: null, bar: { barId: BAR_ID, name: "관악 위스키 바", address: "주소" } })],
    });
    const { router } = renderOwnerWeb(`/bars/${BAR_ID}`);

    expect(await screen.findByText("이 매장을 관리할 권한이 없어요.")).toBeInTheDocument();
    await router.navigate("/applications");
    expect(await card("관악 위스키 바")).toHaveTextContent("지금은 이 매장의 관리 권한이 없어요.");
    expect(screen.queryByRole("link", { name: "매장 관리하기" })).not.toBeInTheDocument();
  });
});
