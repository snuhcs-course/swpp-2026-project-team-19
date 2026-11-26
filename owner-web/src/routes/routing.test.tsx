import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { SESSION_EXPIRED_NOTICE, SIGN_IN_FAILED_NOTICE } from "../auth/SessionProvider";
import { ME, application, bar, errorBody, useOwnerApi } from "../test/api";
import { FakeGateway } from "../test/fakeGateway";
import { renderOwnerWeb } from "../test/render";
import { server } from "../test/server";

const BAR_ID = "22222222-2222-4222-8222-222222222222";
const OTHER_BAR_ID = "33333333-3333-4333-8333-333333333333";

const heading = (name: string) => screen.findByRole("heading", { level: 1, name });

describe("sign-in", () => {
  it("sends a signed-out visitor to sign-in and keeps where they were going", async () => {
    const gateway = new FakeGateway({ signedIn: false });
    const { router } = renderOwnerWeb(`/bars/${BAR_ID}`, { gateway });

    await heading("BottleMap 사장님");
    expect(router.state.location.pathname).toBe("/owner/login");

    await userEvent.click(screen.getByRole("button", { name: "Google로 로그인" }));

    expect(gateway.calls.signIn).toEqual([`${window.location.origin}/owner/`]);
    expect(sessionStorage.getItem("bottlemap-owner-web-return-path")).toBe(`/bars/${BAR_ID}`);
  });

  it("continues to the saved page after the Google round trip", async () => {
    useOwnerApi({ bars: [bar(BAR_ID, "관악 위스키 바")] });
    sessionStorage.setItem("bottlemap-owner-web-return-path", `/bars/${BAR_ID}`);

    const { router } = renderOwnerWeb("/");

    await heading("관악 위스키 바");
    expect(router.state.location.pathname).toBe(`/owner/bars/${BAR_ID}`);
    expect(sessionStorage.getItem("bottlemap-owner-web-return-path")).toBeNull();
  });

  it("links the privacy policy from the sign-in screen", async () => {
    renderOwnerWeb("/login", { gateway: new FakeGateway({ signedIn: false }) });

    await heading("BottleMap 사장님");
    const link = screen.getByRole("link", { name: "개인정보처리방침" });
    expect(link).toHaveAttribute("href", "/privacy");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("links the privacy policy from the footer of a signed-in screen", async () => {
    useOwnerApi({ bars: [bar(BAR_ID, "관악 위스키 바")] });
    renderOwnerWeb(`/bars/${BAR_ID}`);

    await heading("관악 위스키 바");
    expect(screen.getByRole("contentinfo")).toContainElement(screen.getByRole("link", { name: "개인정보처리방침" }));
    expect(screen.getByRole("link", { name: "개인정보처리방침" })).toHaveAttribute("href", "/privacy");
  });

  it("explains that sign-in is unavailable when the server has no Google settings", async () => {
    const gateway = new FakeGateway({ signedIn: false });
    gateway.configured = false;
    renderOwnerWeb("/login", { gateway });

    expect(await screen.findByText("지금은 로그인할 수 없어요. 잠시 후 다시 시도해 주세요.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Google로 로그인" })).toBeDisabled();
  });

  it("removes the redirect parameters and says when Google sign-in failed", async () => {
    window.history.replaceState(null, "", "/owner/?error=access_denied&error_description=denied");
    renderOwnerWeb("/", { gateway: new FakeGateway({ signedIn: false }) });

    expect(await screen.findByText(SIGN_IN_FAILED_NOTICE)).toBeInTheDocument();
    expect(window.location.search).toBe("");
  });

  it("keeps the saved page when Google sign-in fails and the owner tries again", async () => {
    // The owner went to a bar, was sent to sign-in, and Google returned an error to /owner/.
    sessionStorage.setItem("bottlemap-owner-web-return-path", `/bars/${BAR_ID}`);
    window.history.replaceState(null, "", "/owner/?error=server_error");
    const gateway = new FakeGateway({ signedIn: false });
    renderOwnerWeb("/", { gateway });

    expect(await screen.findByText(SIGN_IN_FAILED_NOTICE)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Google로 로그인" }));

    expect(gateway.calls.signIn).toHaveLength(1);
    expect(sessionStorage.getItem("bottlemap-owner-web-return-path")).toBe(`/bars/${BAR_ID}`);
  });

  it("removes the sign-in code from the address bar after a successful sign-in", async () => {
    useOwnerApi();
    window.history.replaceState(null, "", "/owner/?code=pkce-code&keep=1");
    renderOwnerWeb("/");

    await heading("매장 등록");
    expect(window.location.search).toBe("?keep=1");
  });

  it("shows a signed-in visitor of the sign-in page their start screen", async () => {
    useOwnerApi({ bars: [bar(BAR_ID, "관악 위스키 바")] });
    const { router } = renderOwnerWeb("/login");

    await heading("내 매장");
    expect(router.state.location.pathname).toBe("/owner/bars");
  });
});

describe("start screen (src/owner/entry.ts)", () => {
  it("calls GET /api/me before the owner's bars and applications", async () => {
    const calls: string[] = [];
    server.use(
      http.get("/api/me", () => {
        calls.push("me");
        return HttpResponse.json(ME);
      }),
      http.get("/api/me/bars", () => {
        calls.push("bars");
        return HttpResponse.json({ items: [] });
      }),
      http.get("/api/me/owner-applications", () => {
        calls.push("applications");
        return HttpResponse.json({ items: [] });
      }),
    );
    renderOwnerWeb("/");

    await heading("매장 등록");
    expect(calls[0]).toBe("me");
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
  });

  it.each([
    ["an owner with a bar", { bars: [bar(BAR_ID, "관악 위스키 바")], applications: [application("pending")] }, "/owner/bars", "내 매장"],
    ["a pending application", { applications: [application("pending")] }, "/owner/applications", "등록 신청 상태"],
    ["a rejected application", { applications: [application("rejected")] }, "/owner/applications", "등록 신청 상태"],
    ["no application", {}, "/owner/apply/intro", "매장 등록"],
    ["only a canceled application", { applications: [application("canceled")] }, "/owner/apply/intro", "매장 등록"],
  ])("sends %s to the right screen", async (_, api, path, title) => {
    useOwnerApi(api);
    const { router } = renderOwnerWeb("/");

    await heading(title);
    expect(router.state.location.pathname).toBe(path);
  });

  it("shows an error with retry, never registration, when the owner's data fails to load", async () => {
    let failures = 1;
    server.use(
      http.get("/api/me", () => HttpResponse.json(ME)),
      http.get("/api/me/bars", () =>
        failures-- > 0
          ? HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 })
          : HttpResponse.json({ items: [bar(BAR_ID, "관악 위스키 바")] }),
      ),
      http.get("/api/me/owner-applications", () => HttpResponse.json({ items: [] })),
    );
    const { router } = renderOwnerWeb("/");

    expect(await screen.findByText("지금은 서버를 사용할 수 없어요. 잠시 후 다시 시도해 주세요.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/owner/");

    await userEvent.click(screen.getByRole("button", { name: "다시 시도" }));

    await heading("내 매장");
  });

  it("keeps the session when GET /api/me answers 503, and retries", async () => {
    let failures = 1;
    useOwnerApi();
    server.use(
      http.get("/api/me", () =>
        failures-- > 0 ? HttpResponse.json(errorBody("SERVICE_UNAVAILABLE"), { status: 503 }) : HttpResponse.json(ME),
      ),
    );
    const gateway = new FakeGateway();
    renderOwnerWeb("/", { gateway });

    await userEvent.click(await screen.findByRole("button", { name: "다시 시도" }));

    await heading("매장 등록");
    expect(gateway.calls.signOut).toBe(0);
  });
});

describe("access protection", () => {
  it("opens a bar its owner manages", async () => {
    useOwnerApi({ bars: [bar(BAR_ID, "관악 위스키 바")] });
    renderOwnerWeb(`/bars/${BAR_ID}`);

    await heading("관악 위스키 바");
  });

  it("blocks a bar the user does not own", async () => {
    useOwnerApi({ bars: [bar(BAR_ID, "관악 위스키 바")] });
    renderOwnerWeb(`/bars/${OTHER_BAR_ID}`);

    expect(await screen.findByText("이 매장을 관리할 권한이 없어요.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "처음 화면으로" })).toHaveAttribute("href", "/owner");
  });

  it("blocks a bar for a signed-in user with no bars", async () => {
    useOwnerApi({ applications: [application("pending")] });
    renderOwnerWeb(`/bars/${BAR_ID}`);

    expect(await screen.findByText("이 매장을 관리할 권한이 없어요.")).toBeInTheDocument();
  });

  it("offers no retry when the server answers 403", async () => {
    useOwnerApi();
    server.use(http.get("/api/me/bars", () => HttpResponse.json(errorBody("FORBIDDEN"), { status: 403 })));
    const gateway = new FakeGateway();
    renderOwnerWeb(`/bars/${BAR_ID}`, { gateway });

    expect(await screen.findByText("이 화면을 볼 권한이 없어요.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "다시 시도" })).not.toBeInTheDocument();
    expect(gateway.calls.signOut).toBe(0);
  });

  it("shows not-found for an unknown page", async () => {
    renderOwnerWeb("/no-such-page");

    expect(await screen.findByText("페이지를 찾을 수 없어요")).toBeInTheDocument();
  });
});

describe("sign-out and session end", () => {
  it("signs out, forgets the account's data, and shows sign-in", async () => {
    useOwnerApi({ bars: [bar(BAR_ID, "관악 위스키 바")] });
    const { router, queryClient, gateway } = renderOwnerWeb("/");
    await heading("내 매장");

    await userEvent.click(screen.getByRole("button", { name: "로그아웃" }));

    await heading("BottleMap 사장님");
    expect(router.state.location.pathname).toBe("/owner/login");
    expect(gateway.calls.signOut).toBe(1);
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });

  it("returns to sign-in with a notice when the session cannot be refreshed", async () => {
    server.use(http.get("/api/me", () => HttpResponse.json(errorBody("UNAUTHENTICATED"), { status: 401 })));
    const gateway = new FakeGateway();
    gateway.refreshSucceeds = false;
    renderOwnerWeb("/", { gateway });

    expect(await screen.findByText(SESSION_EXPIRED_NOTICE)).toBeInTheDocument();
    expect(gateway.calls.refresh).toBe(1);
    await waitFor(() => expect(gateway.calls.signOut).toBe(1));
  });

  it("drops the previous account's data when another tab signs in as someone else", async () => {
    // Each account sees its own bars; the API tells them apart by the token.
    server.use(
      http.get("/api/me", () => HttpResponse.json(ME)),
      http.get("/api/me/owner-applications", () => HttpResponse.json({ items: [] })),
      http.get("/api/me/bars", ({ request }) =>
        HttpResponse.json({
          items: request.headers.get("Authorization") === "Bearer token-a" ? [bar(BAR_ID, "관악 위스키 바")] : [],
        }),
      ),
    );
    const gateway = new FakeGateway({ userId: "user-a", token: "token-a" });
    renderOwnerWeb(`/bars/${BAR_ID}`, { gateway });
    await heading("관악 위스키 바");

    gateway.switchAccount("user-b", "token-b");

    expect(await screen.findByText("이 매장을 관리할 권한이 없어요.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "관악 위스키 바" })).not.toBeInTheDocument();
  });

  it("keeps the data when the same account signs in again from another tab", async () => {
    let barsCalls = 0;
    useOwnerApi();
    server.use(
      http.get("/api/me/bars", () => {
        barsCalls++;
        return HttpResponse.json({ items: [bar(BAR_ID, "관악 위스키 바")] });
      }),
    );
    const gateway = new FakeGateway({ userId: "user-a" });
    renderOwnerWeb(`/bars/${BAR_ID}`, { gateway });
    await heading("관악 위스키 바");

    gateway.switchAccount("user-a", "token-a2");

    await heading("관악 위스키 바");
    expect(barsCalls).toBe(1);
  });

  it("returns to sign-in when the session ends in another tab", async () => {
    useOwnerApi({ bars: [bar(BAR_ID, "관악 위스키 바")] });
    const { router, gateway, queryClient } = renderOwnerWeb("/");
    await heading("내 매장");

    gateway.endElsewhere();

    await heading("BottleMap 사장님");
    expect(router.state.location.pathname).toBe("/owner/login");
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });
});
