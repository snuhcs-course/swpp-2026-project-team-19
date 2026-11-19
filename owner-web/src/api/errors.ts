import type { components } from "./schema";

type ErrorBody = components["schemas"]["ErrorBody"];
export type FieldError = components["schemas"]["FieldErrorResponse"];

/**
 * An API failure in the common shape {"error": {code, message, details, fieldErrors}} (spec 9.1).
 * Branch on `code`, never on `message`. A request that never got a response is NETWORK_ERROR (status 0),
 * and a response without that shape is HTTP_ERROR.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | null;
  readonly fieldErrors: readonly FieldError[];

  constructor(status: number, body: Partial<ErrorBody> | null, fallbackMessage = "") {
    super(typeof body?.message === "string" && body.message ? body.message : fallbackMessage);
    this.name = "ApiError";
    this.status = status;
    this.code = typeof body?.code === "string" && body.code ? body.code : status === 0 ? "NETWORK_ERROR" : "HTTP_ERROR";
    this.details = body?.details ?? null;
    this.fieldErrors = Array.isArray(body?.fieldErrors) ? body.fieldErrors : [];
  }
}

export function networkError(): ApiError {
  return new ApiError(0, null, "서버에 연결하지 못했어요. 네트워크를 확인해 주세요.");
}

/** The ApiError of a failed response; `body` is what the client parsed (the error document or nothing). */
export function apiErrorFrom(response: Response, body: unknown): ApiError {
  const error = typeof body === "object" && body !== null ? (body as { error?: unknown }).error : undefined;
  return new ApiError(response.status, typeof error === "object" && error !== null ? (error as Partial<ErrorBody>) : null);
}

/** Whether retrying the same request may succeed: no response, or a server-side failure. */
export function isRetryable(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 0 || error.status >= 500);
}

/** The text a screen shows for a failure. The common codes have fixed copy; others use the server's message. */
export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "문제가 생겼어요. 잠시 후 다시 시도해 주세요.";
  switch (error.code) {
    case "NETWORK_ERROR":
      return "서버에 연결하지 못했어요. 네트워크를 확인해 주세요.";
    case "SERVICE_UNAVAILABLE":
      return "지금은 서버를 사용할 수 없어요. 잠시 후 다시 시도해 주세요.";
    case "UNAUTHENTICATED":
      return "로그인이 필요해요.";
    case "FORBIDDEN":
      return "이 화면을 볼 권한이 없어요.";
    default:
      if (error.status >= 500) return "서버에서 문제가 생겼어요. 잠시 후 다시 시도해 주세요.";
      return error.message || "요청을 처리하지 못했어요.";
  }
}

// Copy for fieldErrors[].code, as in the operator dashboard (backend/app/admin/static/app.js).
const FIELD_ERROR_COPY: Record<string, string> = {
  MISSING: "꼭 입력해 주세요.",
  BLANK: "비어 있을 수 없어요.",
  STRING_TOO_SHORT: "비어 있을 수 없어요.",
  STRING_TOO_LONG: "너무 길어요.",
  GREATER_THAN_EQUAL: "허용 범위보다 작아요.",
  LESS_THAN_EQUAL: "허용 범위보다 커요.",
  INT_PARSING: "숫자를 입력해 주세요.",
  INT_TYPE: "숫자를 입력해 주세요.",
  FLOAT_PARSING: "숫자를 입력해 주세요.",
  FLOAT_TYPE: "숫자를 입력해 주세요.",
  INVALID_CHARACTER: "쓸 수 없는 문자가 있어요.",
};

/** The message of each field, keyed by `fieldErrors[].path` (e.g. "displayName", "weeklyHours[1].closeTime"). */
export function fieldErrorMessages(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  const messages: Record<string, string> = {};
  for (const field of error.fieldErrors) {
    if (field.path in messages) continue;
    messages[field.path] = FIELD_ERROR_COPY[field.code] ?? (field.message || "입력값을 확인해 주세요.");
  }
  return messages;
}
