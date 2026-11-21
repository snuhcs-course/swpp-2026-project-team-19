import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { bar, useOwnerApi } from "../test/api";
import { renderOwnerWeb } from "../test/render";
import { server } from "../test/server";
import type { BarDetail } from "./barInfo";

const BAR_ID = "22222222-2222-4222-8222-222222222222";
const user = () => userEvent.setup();
const title = (name: string) => screen.findByRole("heading", { level: 1, name });
const row = (day: string) => screen.getByRole("listitem", { name: `${day}요일` });
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


/** The bar on a server that keeps PATCH /api/bars/{barId}; `answer` may answer instead. */
function hoursServer(initial: Partial<BarDetail> = {}, answer?: (body: Record<string, unknown>) => Response | undefined) {
  let current = bar(BAR_ID, "관악 위스키 바", initial);
  const patches: Record<string, unknown>[] = [];
  useOwnerApi();
  server.use(
    http.get("/api/me/bars", () => HttpResponse.json({ items: [current] })),
    http.get("/api/bars/:barId", () => HttpResponse.json(current)),
    http.patch("/api/bars/:barId", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      patches.push(body);
      const custom = answer?.(body);
      if (custom) return custom;
      current = { ...current, ...(body as Partial<BarDetail>) };
      return HttpResponse.json(current);
    }),
  );
  return { patches };
}

async function openForm() {
  const view = renderOwnerWeb(`/bars/${BAR_ID}/info`);
  await screen.findByRole("button", { name: "저장하기" });
  return view;
}

describe("regular hours in the info form (spec 3.15.1, OwnerInfoHtmlV4Screen.kt)", () => {
  it("shows the hours, marks the next day, and saves them with the form", async () => {
    const api = hoursServer({ weeklyHours: [{ dayOfWeek: 6, closed: true, openTime: null, closeTime: null }] });
    await openForm();

    expect(within(row("토")).getByRole("checkbox", { name: "휴무" })).toBeChecked();
    expect(shownTime("월요일 시작", row("월"))).toBe("");

    await pickTime("월요일 시작", "18:00", row("월"));
    await pickTime("월요일 종료", "02:00", row("월"));
    expect(within(row("월")).getByText("익일")).toBeInTheDocument();
    await user().click(screen.getByRole("button", { name: "평일에 복사" }));
    expect(shownTime("금요일 종료", row("금"))).toBe("02:00");
    await user().click(within(row("일")).getByRole("checkbox", { name: "휴무" }));
    await user().click(screen.getByRole("button", { name: "저장하기" }));

    await title("관악 위스키 바");
    const open = { closed: false, openTime: "18:00", closeTime: "02:00" };
    expect(api.patches).toEqual([
      {
        weeklyHours: [
          { dayOfWeek: 1, ...open },
          { dayOfWeek: 2, ...open },
          { dayOfWeek: 3, ...open },
          { dayOfWeek: 4, ...open },
          { dayOfWeek: 5, ...open },
          { dayOfWeek: 6, closed: true, openTime: null, closeTime: null },
          { dayOfWeek: 7, closed: true, openTime: null, closeTime: null },
        ],
      },
    ]);
  });

  it("brings the times back when a day off is unmarked, and sends none while marked", async () => {
    const api = hoursServer({ weeklyHours: [{ dayOfWeek: 2, closed: false, openTime: "19:00", closeTime: "23:00" }] });
    await openForm();

    await user().click(within(row("화")).getByRole("checkbox", { name: "휴무" }));
    expect(within(row("화")).queryByLabelText("화요일 시작 시")).not.toBeInTheDocument();
    await user().click(within(row("화")).getByRole("checkbox", { name: "휴무" }));
    expect(shownTime("화요일 시작", row("화"))).toBe("19:00");

    await user().click(within(row("화")).getByRole("checkbox", { name: "휴무" }));
    await user().click(screen.getByRole("button", { name: "저장하기" }));

    await title("관악 위스키 바");
    expect(api.patches).toEqual([{ weeklyHours: [{ dayOfWeek: 2, closed: true, openTime: null, closeTime: null }] }]);
  });

  it("leaves a cleared day out, so it has no information", async () => {
    const api = hoursServer({
      weeklyHours: [
        { dayOfWeek: 1, closed: false, openTime: "18:00", closeTime: "23:00" },
        { dayOfWeek: 3, closed: false, openTime: "18:00", closeTime: "23:00" },
      ],
    });
    await openForm();

    await pickTime("월요일 시작", "", row("월"));
    await pickTime("월요일 종료", "", row("월"));
    await user().click(screen.getByRole("button", { name: "저장하기" }));

    await title("관악 위스키 바");
    expect(api.patches).toEqual([{ weeklyHours: [{ dayOfWeek: 3, closed: false, openTime: "18:00", closeTime: "23:00" }] }]);
  });

  it("keeps saving off while a day has only one time", async () => {
    hoursServer();
    await openForm();

    await pickTime("수요일 시작", "18:00", row("수"));

    expect(screen.getByText("영업시간은 5분 단위이며 시작과 종료 시간이 달라야 해요.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "저장하기" })).toBeDisabled();
  });

  it("shows the server's hours error under its weekday", async () => {
    // The second day sent is Friday: weeklyHours[1] is Friday's row.
    hoursServer({}, () =>
      HttpResponse.json(
        {
          error: {
            code: "VALIDATION_FAILED",
            message: "입력값",
            details: null,
            fieldErrors: [{ path: "weeklyHours[1].closeTime", code: "SAME_OPEN_CLOSE", message: "같아요" }],
          },
        },
        { status: 422 },
      ),
    );
    await openForm();

    await pickTime("화요일 시작", "18:00", row("화"));
    await pickTime("화요일 종료", "23:00", row("화"));
    await pickTime("금요일 시작", "18:00", row("금"));
    await pickTime("금요일 종료", "22:00", row("금"));
    await user().click(screen.getByRole("button", { name: "저장하기" }));

    expect(await within(row("금")).findByText("시작과 종료 시간이 달라야 해요.")).toBeInTheDocument();
    expect(within(row("화")).queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("입력한 내용을 확인해 주세요.")).toBeInTheDocument();
  });

  it("does not send the hours when only another field changed", async () => {
    const api = hoursServer({ weeklyHours: [{ dayOfWeek: 1, closed: true, openTime: null, closeTime: null }] });
    await openForm();

    await user().type(screen.getByLabelText("한 줄 소개"), "새 소개");
    await user().click(screen.getByRole("button", { name: "저장하기" }));

    await waitFor(() => expect(api.patches).toEqual([{ description: "새 소개" }]));
  });
});
