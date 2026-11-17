// Operator reset of the daily NTS check and certificate OCR counts (API spec 3.11.19): the
// "요청 수 초기화" tab of the dashboard. Uses the helpers of app.js ($, api, showMessage).
// Data from the API is always put on the page as text (textContent), never as HTML.
"use strict";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const LIMIT_KIND_LABELS = {
  "": "국세청 진위확인과 OCR",
  business_verification: "국세청 진위확인",
  business_certificate_ocr: "사업자등록증 OCR",
};

// `session` drops a response that arrives after sign-out (clearLimits), like the other tabs.
const limits = { session: 0 };

function setLimitsBusy(busy) {
  for (const control of $("limit-user-form").elements) control.disabled = busy;
  $("limit-reset-all").disabled = busy;
}

function setLimitNotice(kind, text) {
  const notice = $("limit-notice");
  notice.className = `notice ${kind}`;
  notice.textContent = text;
  notice.hidden = !text;
}

function setUserIdError(text) {
  const error = $("limit-user-id-error");
  error.textContent = text;
  error.hidden = !text;
  $("limit-user-id").setAttribute("aria-invalid", String(Boolean(text)));
}

function clearedText(count) {
  return count > 0 ? `${count}건 초기화했어요.` : "초기화할 기록이 없어요.";
}

async function resetLimits(body) {
  const session = limits.session;
  setLimitsBusy(true);
  setLimitNotice("", "");
  try {
    const result = await api("POST", "/api/request-limits/reset", body);
    if (session !== limits.session) return;
    setLimitNotice("ok", clearedText(result.clearedCount));
  } catch (error) {
    // On 401 api() has already signed out and shown the login screen.
    if (session !== limits.session || error.status === 401) return;
    handleLimitError(error);
  } finally {
    if (session === limits.session) setLimitsBusy(false);
  }
}

function handleLimitError(error) {
  switch (error.code) {
    case "USER_NOT_FOUND":
      setUserIdError("해당 사용자가 없어요.");
      setLimitNotice("error", "해당 사용자가 없어요. 사용자 ID를 확인하세요.");
      return;
    case "FORBIDDEN":
      showMessage("operator 권한이 없는 계정입니다.");
      return;
    default:
      setLimitNotice("error", error.message);
  }
}

function resetUser(event) {
  event.preventDefault();
  const form = $("limit-user-form");
  const userId = form.elements.userId.value.trim();
  const kind = form.elements.kind.value;
  if (!userId) {
    setUserIdError("사용자 ID를 입력하세요.");
    return;
  }
  if (!UUID_PATTERN.test(userId)) {
    setUserIdError("사용자 ID 형식이 아니에요. 예: 8c1f0b6e-2d3a-4f5b-9c7d-1e2f3a4b5c6d");
    return;
  }
  setUserIdError("");
  if (!window.confirm(`사용자 ${userId}의 ${LIMIT_KIND_LABELS[kind]} 요청 수를 초기화할까요?`)) return;
  resetLimits(kind ? { userId, kind } : { userId });
}

function resetAll() {
  const question = "모든 사용자의 국세청 진위확인과 OCR 요청 수를 초기화할까요? 되돌릴 수 없어요.";
  if (!window.confirm(question)) return;
  // Every user and both kinds: this button takes no kind (3.11.19).
  resetLimits({});
}

function clearLimits() {
  limits.session++;
  setLimitsBusy(false);
  $("limit-user-form").reset();
  setUserIdError("");
  setLimitNotice("", "");
}

// ---------- wiring ----------

$("limit-user-form").addEventListener("submit", resetUser);
$("limit-user-id").addEventListener("input", () => setUserIdError(""));
$("limit-reset-all").addEventListener("click", resetAll);
