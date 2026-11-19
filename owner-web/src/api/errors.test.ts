import { describe, expect, it } from "vitest";
import { ApiError, apiErrorFrom, errorMessage, fieldErrorMessages, isRetryable, networkError } from "./errors";

const response = (status: number) => new Response(null, { status });

describe("ApiError", () => {
  it("reads the common error shape", () => {
    const error = apiErrorFrom(response(422), {
      error: {
        code: "VALIDATION_FAILED",
        message: "입력값을 확인해 주세요.",
        details: { barId: "b1" },
        fieldErrors: [{ path: "displayName", code: "BLANK", message: "blank" }],
      },
    });

    expect(error).toMatchObject({ status: 422, code: "VALIDATION_FAILED", message: "입력값을 확인해 주세요.", details: { barId: "b1" } });
    expect(error.fieldErrors).toHaveLength(1);
  });

  it("is HTTP_ERROR for a response without the error shape", () => {
    expect(apiErrorFrom(response(502), "<html>Bad gateway</html>")).toMatchObject({ status: 502, code: "HTTP_ERROR", fieldErrors: [] });
    expect(apiErrorFrom(response(500), undefined).code).toBe("HTTP_ERROR");
    expect(apiErrorFrom(response(500), { error: "text" }).code).toBe("HTTP_ERROR");
  });

  it("is NETWORK_ERROR when no response came back", () => {
    expect(networkError()).toMatchObject({ status: 0, code: "NETWORK_ERROR" });
  });

  it("is retryable only without a response or for a server error", () => {
    expect(isRetryable(networkError())).toBe(true);
    expect(isRetryable(new ApiError(503, { code: "SERVICE_UNAVAILABLE" }))).toBe(true);
    expect(isRetryable(new ApiError(404, { code: "BAR_NOT_FOUND" }))).toBe(false);
    expect(isRetryable(new ApiError(403, { code: "FORBIDDEN" }))).toBe(false);
    expect(isRetryable(new Error("boom"))).toBe(false);
  });
});

describe("errorMessage", () => {
  it("has fixed copy for the common codes, never the server's text", () => {
    expect(errorMessage(networkError())).toContain("네트워크");
    expect(errorMessage(new ApiError(503, { code: "SERVICE_UNAVAILABLE", message: "JWKS failed" }))).toContain("잠시 후");
    expect(errorMessage(new ApiError(403, { code: "FORBIDDEN", message: "x" }))).toBe("이 화면을 볼 권한이 없어요.");
    expect(errorMessage(new ApiError(401, { code: "UNAUTHENTICATED", message: "x" }))).toBe("로그인이 필요해요.");
    expect(errorMessage(new ApiError(500, { code: "INTERNAL_ERROR", message: "Traceback" }))).not.toContain("Traceback");
  });

  it("shows the server's message for other codes", () => {
    expect(errorMessage(new ApiError(409, { code: "OWNER_APPLICATION_EXISTS", message: "이미 처리 중인 업주 신청이 있습니다." }))).toBe(
      "이미 처리 중인 업주 신청이 있습니다.",
    );
    expect(errorMessage(new ApiError(404, { code: "BAR_NOT_FOUND", message: "" }))).toBe("요청을 처리하지 못했어요.");
    expect(errorMessage(new Error("boom"))).toContain("문제가 생겼어요");
  });
});

describe("fieldErrorMessages", () => {
  it("keys the first message of each field by its path", () => {
    const error = new ApiError(422, {
      code: "VALIDATION_FAILED",
      fieldErrors: [
        { path: "displayName", code: "BLANK", message: "blank" },
        { path: "displayName", code: "STRING_TOO_LONG", message: "long" },
        { path: "weeklyHours[1].closeTime", code: "SOMETHING_NEW", message: "닫는 시간을 확인해 주세요." },
        { path: "phone", code: "SOMETHING_ELSE", message: "" },
      ],
    });

    expect(fieldErrorMessages(error)).toEqual({
      displayName: "비어 있을 수 없어요.",
      "weeklyHours[1].closeTime": "닫는 시간을 확인해 주세요.",
      phone: "입력값을 확인해 주세요.",
    });
    expect(fieldErrorMessages(new Error("boom"))).toEqual({});
  });
});
