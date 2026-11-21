import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { bar, errorBody, useOwnerApi } from "../test/api";
import { renderOwnerWeb } from "../test/render";
import { server } from "../test/server";
import type { OperatingException } from "./operating";
import type { BarDetail } from "./barInfo";

const BAR_ID = "22222222-2222-4222-8222-222222222222";
const SATURDAY = "2026-10-31";
const user = () => userEvent.setup();
const title = (name: string) => screen.findByRole("heading", { level: 1, name });

/** Sets the clock to Seoul local `date` `hh:mm` (only Date is faked; timers run as usual). */
function setSeoulTime(date: string, hour: number, minute = 0) {
  vi.setSystemTime(Date.UTC(Number(date.slice(0, 4)), Number(date.slice(5, 7)) - 1, Number(date.slice(8, 10)), hour - 9, minute));
}

/** The owner's bar on a server that keeps PUT and DELETE /operating-exception (spec 3.15.2, 3.15.3). */
function statusServer(initial: Partial<BarDetail> = {}, answer?: (body: Record<string, unknown> | null) => Response | undefined | Promise<Response | undefined>) {
  let current = bar(BAR_ID, "관악 위스키 바", {
    weeklyHours: [{ dayOfWeek: 6, closed: false, openTime: "18:00", closeTime: "02:00" }],
    ...initial,
  });
  const requests: { method: string; body: Record<string, unknown> | null }[] = [];
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
    http.put("/api/bars/:barId/operating-exception", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      requests.push({ method: "PUT", body });
      const custom = await answer?.(body);
      if (custom) return custom;
      const day = (body.date ?? body.startDate) as string;
      const exception: OperatingException = {
        kind: body.kind as OperatingException["kind"],
        startDate: day,
        endDate: (body.endDate as string | undefined) ?? day,
        openTime: (body.openTime as string | undefined) ?? null,
        closeTime: (body.closeTime as string | undefined) ?? null,
        note: (body.note as string | null) ?? null,
      };
      current = { ...current, operatingException: exception };
      return HttpResponse.json(current);
    }),
    http.delete("/api/bars/:barId/operating-exception", async () => {
      requests.push({ method: "DELETE", body: null });
      const custom = await answer?.(null);
      if (custom) return custom;
      current = { ...current, operatingException: null };
      return HttpResponse.json(current);
    }),
  );
  return { requests, reads, current: () => current };
}

async function openStatus() {
  const view = renderOwnerWeb(`/bars/${BAR_ID}/status`);
  await title("영업 상태 변경");
  await screen.findByRole("radiogroup", { name: "임시 휴무 종류" });
  return view;
}

/** Picks a time in the hour and minute lists named `label` ("" clears it). */
async function pickTime(label: string, time: string, scope: HTMLElement = document.body) {
  await user().selectOptions(within(scope).getByLabelText(`${label} 시`), time.slice(0, 2));
  if (time) await user().selectOptions(within(scope).getByLabelText(`${label} 분`), time.slice(3, 5));
}
/** The time the lists named `label` show, "" for none. */
function shownTime(label: string, scope: HTMLElement = document.body): string {
  const hour = (within(scope).getByLabelText(`${label} 시`) as HTMLSelectElement).value;
  const minute = (within(scope).getByLabelText(`${label} 분`) as HTMLSelectElement).value;
  return hour ? `${hour}:${minute}` : "";
}

const statusCard = () => screen.findByRole("region", { name: "영업 상태" });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  setSeoulTime(SATURDAY, 20);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("home status card (OwnerManagementHomeScreen.kt, spec 3.15.4 and 3.15.5)", () => {
  it("shows the regular status and when the bar closes", async () => {
    statusServer();
    renderOwnerWeb(`/bars/${BAR_ID}`);

    const card = await statusCard();
    expect(card).toHaveTextContent("정상 영업");
    expect(card).toHaveTextContent("영업 중, 익일 02:00 종료");
    expect(within(card).queryByRole("button", { name: "임시 휴무 취소" })).not.toBeInTheDocument();
    expect(within(card).getByRole("link")).toHaveAttribute("href", `/owner/bars/${BAR_ID}/status`);
  });

  it.each([
    ["closed today", { kind: "closed_today", startDate: SATURDAY, endDate: SATURDAY, openTime: null, closeTime: null, note: null }, "오늘 임시 휴무", "임시 휴무"],
    ["changed hours past midnight", { kind: "custom_hours", startDate: SATURDAY, endDate: SATURDAY, openTime: "19:00", closeTime: "01:00", note: null }, "오늘 영업시간 변경", "19:00 ~ 익일 01:00"],
    ["a vacation still to come", { kind: "vacation", startDate: "2026-11-05", endDate: "2026-11-07", note: null, openTime: null, closeTime: null }, "임시 휴업 예정", "11.05 ~ 11.07"],
  ] as const)("shows %s", async (_, operatingException, heading, detail) => {
    statusServer({ operatingException });
    renderOwnerWeb(`/bars/${BAR_ID}`);

    const card = await statusCard();
    expect(within(card).getByRole("heading", { level: 2 })).toHaveTextContent(heading);
    expect(card).toHaveTextContent(detail);
    expect(within(card).getByRole("button", { name: "임시 휴무 취소" })).toBeInTheDocument();
  });

  it("ends a closure after asking, and shows the regular status from the server's answer", async () => {
    const api = statusServer({ operatingException: { kind: "closed_today", startDate: SATURDAY, endDate: SATURDAY, openTime: null, closeTime: null, note: null } });
    renderOwnerWeb(`/bars/${BAR_ID}`);

    await user().click(within(await statusCard()).getByRole("button", { name: "임시 휴무 취소" }));
    const sheet = screen.getByRole("dialog", { name: "임시 휴무를 취소할까요?" });
    expect(within(sheet).getByText("정규 영업시간으로 돌아가요.")).toBeInTheDocument();
    await user().click(within(sheet).getByRole("button", { name: "닫기" }));
    expect(api.requests).toEqual([]);

    await user().click(within(await statusCard()).getByRole("button", { name: "임시 휴무 취소" }));
    const reads = { ...api.reads };
    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "취소하기" }));

    await waitFor(async () => expect(await statusCard()).toHaveTextContent("정상 영업"));
    expect(api.requests).toEqual([{ method: "DELETE", body: null }]);
    await waitFor(() => expect(api.reads.myBars).toBeGreaterThan(reads.myBars));
    expect(api.reads.bar).toBeGreaterThan(reads.bar);
  });

  it("keeps the closure and says so when ending it fails", async () => {
    statusServer(
      { operatingException: { kind: "closed_today", startDate: SATURDAY, endDate: SATURDAY, openTime: null, closeTime: null, note: null } },
      () => HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 }),
    );
    renderOwnerWeb(`/bars/${BAR_ID}`);

    await user().click(within(await statusCard()).getByRole("button", { name: "임시 휴무 취소" }));
    await user().click(within(screen.getByRole("dialog")).getByRole("button", { name: "취소하기" }));

    expect(await screen.findByText("서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")).toBeInTheDocument();
    expect(await statusCard()).toHaveTextContent("오늘 임시 휴무");
  });
});

describe("operating status page (OwnerOperatingQuickScreen, spec 3.15.2)", () => {
  async function applyWithSheet() {
    await user().click(screen.getByRole("button", { name: /적용$/ }));
    const sheet = screen.getByRole("dialog", { name: "임시 휴무를 적용할까요?" });
    expect(within(sheet).getByText("지금 설정된 임시 휴무가 있으면 이 내용으로 바뀌어요.")).toBeInTheDocument();
    await user().click(within(sheet).getByRole("button", { name: "적용하기" }));
  }

  it("closes today after asking, with Seoul's date and the note, and returns home", async () => {
    const api = statusServer();
    const { router } = await openStatus();

    await user().click(screen.getByRole("radio", { name: /오늘 휴무/ }));
    await user().type(screen.getByLabelText("고객 안내 (선택)"), "  내부 사정으로 쉽니다 ");
    expect(screen.getByRole("button", { name: "휴무 적용" })).toBeEnabled();
    await applyWithSheet();

    await title("관악 위스키 바");
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}`);
    expect(api.requests).toEqual([{ method: "PUT", body: { kind: "closed_today", date: SATURDAY, note: "내부 사정으로 쉽니다" } }]);
    expect(await statusCard()).toHaveTextContent("오늘 임시 휴무");
  });

  it("changes today's hours, past midnight too", async () => {
    const api = statusServer();
    await openStatus();

    await user().click(screen.getByRole("radio", { name: /오늘만 영업시간 변경/ }));
    expect(shownTime("영업 시작")).toBe("18:00");
    expect(shownTime("영업 종료")).toBe("21:30");
    await pickTime("영업 시작", "20:00");
    await pickTime("영업 종료", "01:00");
    expect(screen.getByText("종료는 다음 날 01:00이에요.")).toBeInTheDocument();
    await applyWithSheet();

    await title("관악 위스키 바");
    expect(api.requests[0]?.body).toEqual({ kind: "custom_hours", date: SATURDAY, openTime: "20:00", closeTime: "01:00", note: null });
  });

  it("refuses the same opening and closing time", async () => {
    statusServer();
    await openStatus();

    await user().click(screen.getByRole("radio", { name: /오늘만 영업시간 변경/ }));
    await pickTime("영업 종료", "18:00");

    expect(screen.getByText("영업 시작과 종료 시각이 같을 수 없어요.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "변경 적용" })).toBeDisabled();
  });

  it("closes for a range of days, picked from today on", async () => {
    const api = statusServer();
    await openStatus();

    await user().click(screen.getByRole("radio", { name: /기간 임시 휴업/ }));
    expect(screen.getByLabelText("시작일")).toHaveAttribute("min", SATURDAY);
    expect(screen.getByRole("button", { name: "휴업 적용" })).toBeDisabled();
    await user().type(screen.getByLabelText("시작일"), "2026-11-05");
    await user().type(screen.getByLabelText("종료일"), "2026-11-07");
    // A start after the end clears the end, as the app's calendar does.
    await user().clear(screen.getByLabelText("시작일"));
    await user().type(screen.getByLabelText("시작일"), "2026-11-08");
    expect(screen.getByLabelText("종료일")).toHaveValue("");
    await user().type(screen.getByLabelText("종료일"), "2026-11-09");
    await applyWithSheet();

    await title("관악 위스키 바");
    expect(api.requests[0]?.body).toEqual({ kind: "vacation", startDate: "2026-11-08", endDate: "2026-11-09", note: null });
    expect(await statusCard()).toHaveTextContent("임시 휴업 예정");
  });

  it("sends the date of the moment the owner applies, after Seoul's midnight too", async () => {
    // ownerQuickApplyDay: the screen opened before midnight, the button is pressed after.
    setSeoulTime(SATURDAY, 23, 59);
    const api = statusServer();
    await openStatus();
    await user().click(screen.getByRole("radio", { name: /오늘 휴무/ }));
    await user().click(screen.getByRole("button", { name: "휴무 적용" }));

    // Midnight passes while the confirm sheet is open; the date is read at the press itself.
    setSeoulTime("2026-11-01", 0, 1);
    await user().click(within(screen.getByRole("dialog", { name: "임시 휴무를 적용할까요?" })).getByRole("button", { name: "적용하기" }));

    await title("관악 위스키 바");
    expect(api.requests[0]?.body).toMatchObject({ kind: "closed_today", date: "2026-11-01" });
  });

  it("refuses a vacation that starts before the day it is applied", async () => {
    // validQuickVacationAtApply at the moment of applying.
    setSeoulTime(SATURDAY, 23, 59);
    const api = statusServer();
    await openStatus();
    await user().click(screen.getByRole("radio", { name: /기간 임시 휴업/ }));
    await user().type(screen.getByLabelText("시작일"), SATURDAY);
    await user().type(screen.getByLabelText("종료일"), "2026-11-02");
    await user().click(screen.getByRole("button", { name: "휴업 적용" }));

    setSeoulTime("2026-11-01", 0, 1);
    await user().click(within(screen.getByRole("dialog", { name: "임시 휴무를 적용할까요?" })).getByRole("button", { name: "적용하기" }));

    expect(await screen.findByText("시작일과 종료일을 다시 확인해 주세요.")).toBeInTheDocument();
    expect(api.requests).toEqual([]);
  });

  it("uses Seoul's date whatever the browser's time zone", async () => {
    const original = process.env.TZ;
    process.env.TZ = "America/Los_Angeles";
    try {
      // 01:00 on Sunday in Seoul is still Saturday in Los Angeles.
      setSeoulTime("2026-11-01", 1);
      const api = statusServer();
      await openStatus();
      await user().click(screen.getByRole("radio", { name: /오늘 휴무/ }));
      await applyWithSheet();

      await title("관악 위스키 바");
      expect(api.requests[0]?.body).toMatchObject({ date: "2026-11-01" });
    } finally {
      process.env.TZ = original;
    }
  });

  it("says the date changed when the server's today differs (DATE_NOT_TODAY), keeping the choice", async () => {
    statusServer({}, () =>
      HttpResponse.json(
        { error: { code: "VALIDATION_FAILED", message: "날짜", details: null, fieldErrors: [{ path: "date", code: "DATE_NOT_TODAY", message: "오늘" }] } },
        { status: 422 },
      ),
    );
    await openStatus();
    await user().click(screen.getByRole("radio", { name: /오늘 휴무/ }));
    await applyWithSheet();

    expect(await screen.findByText("날짜가 바뀌었어요. 확인한 뒤 다시 적용해 주세요.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /오늘 휴무/ })).toHaveAttribute("aria-checked", "true");
  });

  it("shows a past start under its field (DATE_IN_PAST)", async () => {
    statusServer({}, () =>
      HttpResponse.json(
        { error: { code: "VALIDATION_FAILED", message: "날짜", details: null, fieldErrors: [{ path: "startDate", code: "DATE_IN_PAST", message: "과거" }] } },
        { status: 422 },
      ),
    );
    await openStatus();
    await user().click(screen.getByRole("radio", { name: /기간 임시 휴업/ }));
    await user().type(screen.getByLabelText("시작일"), "2026-11-05");
    await user().type(screen.getByLabelText("종료일"), "2026-11-07");
    await applyWithSheet();

    expect(await screen.findByText("시작일이 지났어요. 날짜를 다시 골라 주세요.")).toBeInTheDocument();
  });

  it("keeps the choice after a server error, and applies on the next try", async () => {
    let failures = 1;
    const api = statusServer({}, () => (failures-- > 0 ? HttpResponse.json(errorBody("INTERNAL_ERROR"), { status: 500 }) : undefined));
    await openStatus();
    await user().click(screen.getByRole("radio", { name: /오늘 휴무/ }));
    await applyWithSheet();

    expect(await screen.findByText("서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")).toBeInTheDocument();
    await applyWithSheet();

    await title("관악 위스키 바");
    expect(api.requests).toHaveLength(2);
  });

  it("goes to the bar list when the bar is gone (404)", async () => {
    statusServer({}, () => HttpResponse.json(errorBody("BAR_NOT_FOUND"), { status: 404 }));
    const { router } = await openStatus();
    await user().click(screen.getByRole("radio", { name: /오늘 휴무/ }));
    await applyWithSheet();

    await waitFor(() => expect(router.state.location.pathname).toBe("/owner/bars"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes the bar's screens when the owner lost it (403)", async () => {
    let owned = true;
    const api = statusServer({}, () => {
      owned = false;
      return HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 });
    });
    server.use(http.get("/api/me/bars", () => HttpResponse.json({ items: owned ? [api.current()] : [] })));
    await openStatus();
    await user().click(screen.getByRole("radio", { name: /오늘 휴무/ }));
    await applyWithSheet();

    expect(await screen.findByRole("link", { name: "처음 화면으로" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
  });

  it("sends one request while the answer is slow, and refuses to leave meanwhile", async () => {
    let answer: (() => void) | null = null;
    const api = statusServer({}, async () => {
      await new Promise<void>((resolve) => (answer = resolve));
      return undefined;
    });
    const { router } = await openStatus();
    await user().click(screen.getByRole("radio", { name: /오늘 휴무/ }));
    await applyWithSheet();
    await waitFor(() => expect(answer).not.toBeNull());

    const confirm = within(screen.getByRole("dialog", { name: "임시 휴무를 적용할까요?" })).getByRole("button", { name: "적용하기" });
    expect(confirm).toBeDisabled();
    await user().click(screen.getByRole("button", { name: "뒤로" }));
    expect(screen.queryByRole("dialog", { name: "변경을 취소할까요?" })).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}/status`);

    answer!();

    await title("관악 위스키 바");
    expect(api.requests).toHaveLength(1);
  });

  it("asks before leaving with a choice made, and leaves at once without one", async () => {
    statusServer();
    await openStatus();

    await user().click(screen.getByRole("button", { name: "뒤로" }));
    await title("관악 위스키 바");

    await user().click(await screen.findByRole("link", { name: /영업 상태 변경/ }));
    await user().click(await screen.findByRole("radio", { name: /오늘 휴무/ }));
    await user().click(screen.getByRole("button", { name: "뒤로" }));

    const sheet = await screen.findByRole("dialog", { name: "변경을 취소할까요?" });
    expect(within(sheet).getByText("저장하지 않은 수정 사항은 사라집니다.")).toBeInTheDocument();
    await user().click(within(sheet).getByRole("button", { name: "변경 취소" }));
    await title("관악 위스키 바");
  });
});
