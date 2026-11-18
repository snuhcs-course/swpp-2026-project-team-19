import { describe, expect, it, vi } from "vitest";
import { FakeGateway } from "../test/fakeGateway";
import { createAuthFetch } from "./authFetch";
import { ApiError } from "./errors";

const URL = "http://localhost/api/me";

/** A fetch that answers from `statuses` in order and records the token and body of each request. */
function scriptedFetch(...statuses: number[]) {
  const seen: { authorization: string | null; body: string }[] = [];
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const request = input as Request;
    seen.push({ authorization: request.headers.get("Authorization"), body: await request.text() });
    return new Response(null, { status: statuses.shift() ?? 200 });
  });
  return { fetch: fetch as unknown as typeof globalThis.fetch, seen, calls: fetch };
}

describe("createAuthFetch (spec 3.1.5)", () => {
  it("adds the current access token", async () => {
    const api = scriptedFetch(200);
    const send = createAuthFetch(new FakeGateway({ token: "t1" }), vi.fn(), api.fetch);

    const response = await send(new Request(URL));

    expect(response.status).toBe(200);
    expect(api.seen[0]?.authorization).toBe("Bearer t1");
  });

  it("sends no Authorization header without a session", async () => {
    const api = scriptedFetch(200);
    await createAuthFetch(new FakeGateway({ signedIn: false }), vi.fn(), api.fetch)(new Request(URL));

    expect(api.seen[0]?.authorization).toBeNull();
  });

  it("refreshes once on 401 and resends the same request with the new token", async () => {
    const api = scriptedFetch(401, 200);
    const gateway = new FakeGateway({ token: "old" });
    const expired = vi.fn();

    const response = await createAuthFetch(gateway, expired, api.fetch)(
      new Request(URL, { method: "PATCH", body: JSON.stringify({ displayName: "새 이름" }) }),
    );

    expect(response.status).toBe(200);
    expect(gateway.calls.refresh).toBe(1);
    expect(api.seen.map((request) => request.authorization)).toEqual(["Bearer old", "Bearer refreshed-token"]);
    expect(api.seen[1]?.body).toBe('{"displayName":"새 이름"}');
    expect(expired).not.toHaveBeenCalled();
  });

  it("shares one refresh between requests that get 401 at the same time", async () => {
    const api = scriptedFetch(401, 401, 401, 200, 200, 200);
    const gateway = new FakeGateway();
    const send = createAuthFetch(gateway, vi.fn(), api.fetch);

    const responses = await Promise.all([send(new Request(URL)), send(new Request(URL)), send(new Request(URL))]);

    expect(responses.map((response) => response.status)).toEqual([200, 200, 200]);
    expect(gateway.calls.refresh).toBe(1);
  });

  it("ends the session when the refresh fails", async () => {
    const api = scriptedFetch(401);
    const gateway = new FakeGateway();
    gateway.refreshSucceeds = false;
    const expired = vi.fn();

    const response = await createAuthFetch(gateway, expired, api.fetch)(new Request(URL));

    expect(response.status).toBe(401);
    expect(expired).toHaveBeenCalledOnce();
    expect(api.calls).toHaveBeenCalledOnce();
  });

  it("ends the session when the resent request gets 401 again, without a second retry", async () => {
    const api = scriptedFetch(401, 401, 200);
    const expired = vi.fn();

    const response = await createAuthFetch(new FakeGateway(), expired, api.fetch)(new Request(URL));

    expect(response.status).toBe(401);
    expect(expired).toHaveBeenCalledOnce();
    expect(api.calls).toHaveBeenCalledTimes(2);
  });

  it.each([403, 503])("keeps the session on %i", async (status) => {
    const api = scriptedFetch(status);
    const gateway = new FakeGateway();
    const expired = vi.fn();

    const response = await createAuthFetch(gateway, expired, api.fetch)(new Request(URL));

    expect(response.status).toBe(status);
    expect(gateway.calls.refresh).toBe(0);
    expect(expired).not.toHaveBeenCalled();
  });

  it("throws NETWORK_ERROR when the request never reaches the server", async () => {
    const failing = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof globalThis.fetch;

    await expect(createAuthFetch(new FakeGateway(), vi.fn(), failing)(new Request(URL))).rejects.toMatchObject({
      constructor: ApiError,
      code: "NETWORK_ERROR",
    });
  });

  it("rethrows the abort of a cancelled request instead of calling it a network failure", async () => {
    const controller = new AbortController();
    const fetch = vi.fn(async () => {
      controller.abort();
      throw new DOMException("aborted", "AbortError");
    }) as unknown as typeof globalThis.fetch;

    await expect(
      createAuthFetch(new FakeGateway(), vi.fn(), fetch)(new Request(URL, { signal: controller.signal })),
    ).rejects.toMatchObject({ name: "AbortError" });
  });
});
