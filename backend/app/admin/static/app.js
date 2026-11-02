// Operator dashboard for owner applications (API spec 3.11.4, 3.11.6-3.11.8, 3.11.13).
// Data from the API is always put on the page as text (textContent), never as HTML.
"use strict";

const config = window.BOTTLEMAP_ADMIN_CONFIG || {};
const TEMP_TOKEN_KEY = "bottlemap-admin-temp-token";
const PAGE_SIZE = 20;
const DEFAULT_FILTERS = { status: "pending", applicationType: "", verificationResult: "" };

const LABELS = {
  status: { pending: "대기", approved: "승인됨", rejected: "거절됨", canceled: "취소됨" },
  applicationType: { existing_bar: "기존 업장", new_bar: "새 업장" },
  verification: { matched: "일치", not_matched: "불일치", unavailable: "확인 못 함" },
  businessStatus: { active: "계속사업자", suspended: "휴업자", closed: "폐업자" },
};

const FIELD_ERROR_TEXT = {
  MISSING: "필수 항목입니다.",
  STRING_TOO_SHORT: "비어 있을 수 없습니다.",
  BLANK: "비어 있을 수 없습니다.",
  STRING_TOO_LONG: "너무 깁니다.",
  GREATER_THAN_EQUAL: "허용 범위보다 작습니다.",
  LESS_THAN_EQUAL: "허용 범위보다 큽니다.",
  FLOAT_PARSING: "숫자를 입력하세요.",
  FLOAT_TYPE: "숫자를 입력하세요.",
  EXTRA_FORBIDDEN: "보낼 수 없는 항목입니다.",
};

const supabaseClient =
  config.supabaseUrl && config.supabasePublishableKey && window.supabase
    ? window.supabase.createClient(config.supabaseUrl, config.supabasePublishableKey, {
        auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
      })
    : null;

const state = {
  filters: { ...DEFAULT_FILTERS },
  items: [],
  nextCursor: null,
  listRequest: 0,
  selectedId: null,
  detail: null,
  detailRequest: 0,
  photosRefreshed: false,
  busy: false,
  notice: null,
};

// ---------- small DOM helpers ----------

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

function showView(name) {
  for (const view of ["loading", "login", "message", "dashboard"]) {
    $(`view-${view}`).hidden = view !== name;
  }
}

function showMessage(text, retry) {
  $("message-text").textContent = text;
  const button = $("message-retry");
  button.hidden = !retry;
  button.onclick = retry || null;
  showView("message");
}

const seoulTime = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function formatTime(value) {
  return value ? seoulTime.format(new Date(value)) : "-";
}

function formatBusinessNumber(value) {
  return /^\d{10}$/.test(value || "") ? `${value.slice(0, 3)}-${value.slice(3, 5)}-${value.slice(5)}` : value || "-";
}

function label(group, value) {
  return value ? LABELS[group][value] || value : "-";
}

function badge(group, value) {
  return el("span", { class: `badge ${value || ""}` }, label(group, value));
}

function barOf(application) {
  return application.bar || application.proposedBar || { name: "-", address: "-" };
}

// ---------- API ----------

class ApiError extends Error {
  constructor(status, body) {
    const error = (body && body.error) || {};
    super(error.message || `요청이 실패했습니다 (HTTP ${status}).`);
    this.status = status;
    this.code = error.code || (status === 0 ? "NETWORK_ERROR" : "HTTP_ERROR");
    this.details = error.details || null;
    this.fieldErrors = error.fieldErrors || [];
  }
}

function readTempToken() {
  try {
    return sessionStorage.getItem(TEMP_TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeTempToken(token) {
  try {
    if (token) sessionStorage.setItem(TEMP_TOKEN_KEY, token);
    else sessionStorage.removeItem(TEMP_TOKEN_KEY);
  } catch {
    // Without storage the temporary login lasts until the page is reloaded.
  }
  memoryTempToken = token;
}

let memoryTempToken = readTempToken();

async function accessToken() {
  if (memoryTempToken) return memoryTempToken;
  if (!supabaseClient) return null;
  const { data } = await supabaseClient.auth.getSession();
  return data.session ? data.session.access_token : null;
}

// Concurrent 401s share one refresh (spec 3.1.5).
let refreshing = null;
function refreshSession() {
  if (memoryTempToken || !supabaseClient) return Promise.resolve(false);
  if (!refreshing) {
    refreshing = supabaseClient.auth
      .refreshSession()
      .then(({ data, error }) => !error && Boolean(data.session))
      .catch(() => false)
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

async function api(method, path, body, retried = false) {
  const token = await accessToken();
  const headers = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response;
  try {
    response = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, { error: { message: "서버에 연결하지 못했습니다. 네트워크를 확인해 주세요." } });
  }
  const data = await response.json().catch(() => null);
  if (response.ok) return data;

  if (response.status === 401) {
    if (!retried && (await refreshSession())) return api(method, path, body, true);
    await signOut();
    showLogin("로그인이 만료되었습니다. 다시 로그인해 주세요.");
  }
  throw new ApiError(response.status, data);
}

// Approve and reject record the operator, who needs a users row; GET /api/me creates it (3.11.7).
async function withUsersRow(call) {
  try {
    return await call();
  } catch (error) {
    if (error.code !== "USER_NOT_FOUND") throw error;
    await api("GET", "/api/me");
    return call();
  }
}

// ---------- sign-in ----------

function showLogin(message) {
  $("account").hidden = true;
  const text = $("login-message");
  text.textContent = message || "";
  text.hidden = !message;
  $("login-google").disabled = !supabaseClient;
  if (!supabaseClient && !message) {
    text.textContent = "서버에 Google 로그인 설정(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)이 없습니다.";
    text.hidden = false;
  }
  $("login-temp").hidden = !config.tempLoginEnabled;
  showView("login");
}

async function signOut() {
  writeTempToken(null);
  if (supabaseClient) {
    // Drop the stored session even if Supabase cannot be reached (spec 3.1.2).
    await supabaseClient.auth.signOut({ scope: "local" }).catch(() => {});
  }
}

async function loginWithGoogle() {
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: `${location.origin}/admin/` },
  });
  if (error) showLogin("Google 로그인을 시작하지 못했습니다. 잠시 후 다시 시도해 주세요.");
}

async function loginTemporarily() {
  try {
    const data = await api("POST", "/api/auth/temp-login");
    writeTempToken(data.accessToken);
    await start();
  } catch (error) {
    showLogin(error.message);
  }
}

async function start() {
  showView("loading");
  const token = await accessToken();
  // supabase-js has exchanged the OAuth code in the URL by now; keep it out of the address bar.
  if (new URLSearchParams(location.search).has("code")) history.replaceState(null, "", location.pathname);
  if (!token) {
    showLogin();
    return;
  }
  let me;
  try {
    me = await api("GET", "/api/me");
  } catch (error) {
    if (error.status === 401) return; // api() already showed the login screen
    // 503 SERVICE_UNAVAILABLE keeps the session (spec 3.1.5).
    showMessage(error.message, start);
    return;
  }
  $("account-email").textContent = me.email || me.displayName || "";
  $("account").hidden = false;
  if (me.userType !== "operator") {
    showMessage("operator 권한이 없는 계정입니다. 운영자 계정으로 다시 로그인하세요.");
    return;
  }
  showView("dashboard");
  loadList(true);
}

// ---------- list (3.11.6) ----------

function listQuery() {
  const params = new URLSearchParams({ status: state.filters.status, limit: String(PAGE_SIZE) });
  if (state.filters.applicationType) params.set("applicationType", state.filters.applicationType);
  if (state.filters.verificationResult) params.set("verificationResult", state.filters.verificationResult);
  if (state.nextCursor) params.set("cursor", state.nextCursor);
  return params;
}

function setListStatus(text, retry) {
  $("list-status").textContent = text;
  $("list-retry").hidden = !retry;
  $("list-retry").onclick = retry || null;
}

async function loadList(reset) {
  if (reset) {
    state.items = [];
    state.nextCursor = null;
    renderRows();
  }
  const request = ++state.listRequest;
  $("load-more").hidden = true;
  setListStatus("불러오는 중...");
  try {
    const page = await api("GET", `/api/owner-applications?${listQuery()}`);
    if (request !== state.listRequest) return;
    state.items = state.items.concat(page.items);
    state.nextCursor = page.nextCursor;
    renderRows();
    setListStatus(state.items.length ? `${state.items.length}건${state.nextCursor ? " (더 있음)" : ""}` : "조건에 맞는 신청이 없습니다.");
    $("load-more").hidden = !state.nextCursor;
  } catch (error) {
    if (request !== state.listRequest || error.status === 401) return;
    const filtered = state.nextCursor || JSON.stringify(state.filters) !== JSON.stringify(DEFAULT_FILTERS);
    if (error.code === "VALIDATION_FAILED" && filtered) {
      // A filter or cursor the server does not accept: start over from the defaults (3.11.6).
      state.filters = { ...DEFAULT_FILTERS };
      writeFilters();
      loadList(true);
      return;
    }
    if (error.code === "FORBIDDEN") {
      showMessage("operator 권한이 없는 계정입니다.");
      return;
    }
    setListStatus(error.message, () => loadList(false));
  }
}

function writeFilters() {
  const form = $("filters");
  for (const [name, value] of Object.entries(state.filters)) form.elements[name].value = value;
}

function renderRows() {
  const rows = state.items.map((item) => {
    const row = el(
      "tr",
      {
        tabindex: "0",
        class: item.applicationId === state.selectedId ? "selected" : null,
        onclick: () => openDetail(item.applicationId),
        onkeydown: (event) => {
          if (event.key === "Enter") openDetail(item.applicationId);
        },
      },
      el("td", {}, formatTime(item.createdAt)),
      el("td", {}, label("applicationType", item.applicationType)),
      el("td", {}, barOf(item).name),
      el("td", {}, item.applicant.displayName || item.applicant.email || "-"),
      el("td", {}, badge("status", item.status)),
      el("td", {}, item.businessVerification ? badge("verification", item.businessVerification.result) : "-"),
      el("td", {}, String(item.menuPhotos.length)),
    );
    return row;
  });
  $("rows").replaceChildren(...rows);
}

function replaceListItem(application) {
  const index = state.items.findIndex((item) => item.applicationId === application.applicationId);
  if (index >= 0) state.items[index] = application;
  renderRows();
}

// ---------- detail (3.11.4) ----------

async function openDetail(applicationId, notice = null) {
  if (state.selectedId !== applicationId) state.photosRefreshed = false;
  state.selectedId = applicationId;
  state.notice = notice;
  renderRows();
  const request = ++state.detailRequest;
  if (!state.detail || state.detail.applicationId !== applicationId) {
    $("detail").replaceChildren(el("p", { class: "placeholder" }, "불러오는 중..."));
  }
  try {
    const application = await api("GET", `/api/owner-applications/${encodeURIComponent(applicationId)}`);
    if (request !== state.detailRequest) return;
    state.detail = application;
    replaceListItem(application);
    renderDetail();
  } catch (error) {
    if (request !== state.detailRequest || error.status === 401) return;
    if (error.code === "OWNER_APPLICATION_NOT_FOUND") {
      closeDetail("신청을 찾을 수 없습니다. 목록을 다시 불러옵니다.");
      loadList(true);
      return;
    }
    $("detail").replaceChildren(
      el("p", { class: "notice error" }, error.message),
      el("button", { type: "button", onclick: () => openDetail(applicationId) }, "다시 시도"),
    );
  }
}

function closeDetail(message) {
  state.selectedId = null;
  state.detail = null;
  renderRows();
  $("detail").replaceChildren(el("p", { class: "placeholder" }, message || "목록에서 신청을 고르세요."));
}

function fields(pairs) {
  return el("dl", { class: "fields" }, pairs.flatMap(([name, value]) => [el("dt", {}, name), el("dd", {}, value ?? "-")]));
}

function mapSearchLink(address) {
  return el(
    "a",
    { href: `https://map.kakao.com/?q=${encodeURIComponent(address)}`, target: "_blank", rel: "noopener noreferrer" },
    "카카오맵에서 주소 확인",
  );
}

function renderDetail() {
  const app = state.detail;
  if (!app) return;
  const verification = app.businessVerification;
  const bar = barOf(app);
  const pending = app.status === "pending";

  const children = [
    el("h2", {}, bar.name),
    el("div", { class: "action-row" }, badge("status", app.status), label("applicationType", app.applicationType)),
  ];
  if (state.notice) children.push(el("p", { class: `notice ${state.notice.kind}` }, state.notice.text));

  children.push(el("h3", {}, "신청 정보"));
  children.push(
    fields([
      ["신청자", [app.applicant.displayName, app.applicant.email].filter(Boolean).join(" / ") || "-"],
      ["연락처", app.contactPhone],
      ["메모", app.applicantNote],
      ["신청 시각", formatTime(app.createdAt)],
      ["처리 시각", formatTime(app.reviewedAt)],
      ...(app.rejectionReason ? [["거절 사유", app.rejectionReason]] : []),
    ]),
  );

  children.push(el("h3", {}, app.bar ? "업장" : "신청한 새 업장"));
  children.push(
    fields([
      ["이름", bar.name],
      ["주소", el("span", {}, bar.address, " ", mapSearchLink(bar.address))],
      ...(app.proposedBar ? [["전화", app.proposedBar.phone]] : []),
    ]),
  );

  children.push(el("h3", {}, "사업자등록 검증"));
  children.push(
    fields([
      ["사업자등록번호", formatBusinessNumber(app.businessRegistrationNumber)],
      ["대표자명", app.representativeName],
      ["개업일자", app.openingDate],
      ["검증 결과", verification ? badge("verification", verification.result) : "-"],
      ["검증 시각", verification ? formatTime(verification.checkedAt) : "-"],
      ["사업자 상태", label("businessStatus", app.businessStatus)],
    ]),
  );

  children.push(el("h3", {}, `메뉴판 사진 (${app.menuPhotos.length})`));
  children.push(renderPhotos(app));

  if (pending) {
    children.push(el("h3", {}, "처리"));
    children.push(renderActions(app));
  }
  $("detail").replaceChildren(...children);
}

function renderPhotos(app) {
  if (!app.menuPhotos.length) return el("p", { class: "placeholder" }, "올린 사진이 없습니다.");
  return el(
    "div",
    { class: "photos" },
    app.menuPhotos.map((photo) =>
      el(
        "a",
        { href: photo.imageUrl, target: "_blank", rel: "noopener noreferrer" },
        el("img", {
          src: photo.imageUrl,
          alt: `메뉴판 사진 ${photo.imageOrder}`,
          loading: "lazy",
          // A signed URL may have expired; the detail API hands out fresh ones (3.11.1). Once per opening.
          onerror: () => {
            if (state.photosRefreshed) return;
            state.photosRefreshed = true;
            openDetail(app.applicationId, state.notice);
          },
        }),
      ),
    ),
  );
}

// ---------- actions (3.11.7, 3.11.8, 3.11.13) ----------

function renderActions(app) {
  const result = app.businessVerification ? app.businessVerification.result : null;
  const box = el("div", { class: "actions" });

  if (result === "unavailable") {
    box.append(
      el(
        "p",
        { class: "notice warn" },
        "국세청 검증을 하지 못한 신청입니다. 승인하기 전에 먼저 사업자등록 정보를 다시 확인하세요.",
      ),
    );
  } else if (result === "not_matched") {
    box.append(el("p", { class: "notice error" }, "사업자등록 정보가 국세청 정보와 맞지 않습니다. 거절을 검토하세요."));
  }

  box.append(
    el(
      "div",
      { class: "action-row" },
      el(
        "button",
        { type: "button", class: result === "unavailable" ? null : "secondary", onclick: () => verifyBusiness(app) },
        "사업자등록 정보 다시 확인",
      ),
    ),
  );

  box.append(app.applicationType === "new_bar" ? newBarApproveForm(app) : existingBarApproveRow(app));
  box.append(rejectForm(app));
  return box;
}

function existingBarApproveRow(app) {
  return el(
    "div",
    { class: "action-row" },
    el("button", { type: "button", onclick: () => approve(app, {}) }, "승인"),
    el("span", { class: "hint" }, "승인하면 신청자가 이 업장의 업주가 됩니다."),
  );
}

const BAR_FIELDS = [
  ["name", "이름", "text"],
  ["address", "주소", "text"],
  ["latitude", "위도", "text"],
  ["longitude", "경도", "text"],
  ["phone", "전화", "text"],
];

function newBarApproveForm(app) {
  const proposed = app.proposedBar || {};
  const form = el("form", { class: "form-grid", novalidate: true });
  for (const [name, text, type] of BAR_FIELDS) {
    const input = el("input", {
      name,
      type,
      value: proposed[name] ?? "",
      inputmode: name === "latitude" || name === "longitude" ? "decimal" : null,
      placeholder: name === "latitude" ? "37.484102" : name === "longitude" ? "126.929815" : null,
    });
    form.append(el("label", {}, text), input, el("div", { class: "field-error", "data-for": name, hidden: true }));
  }
  // Pasting "37.48, 126.92" copied from a map fills both coordinates.
  form.elements.latitude.addEventListener("paste", (event) => {
    const text = (event.clipboardData || window.clipboardData).getData("text");
    const match = text.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (!match) return;
    event.preventDefault();
    form.elements.latitude.value = match[1];
    form.elements.longitude.value = match[2];
  });
  form.append(
    el("span"),
    el("span", { class: "hint" }, "주소를 지도에서 확인하고 좌표를 입력하세요. 위도 칸에 \"위도, 경도\"를 붙여 넣으면 둘 다 채워집니다."),
    el("span"),
    el("div", { class: "action-row" }, el("button", { type: "submit" }, "확인한 정보로 승인")),
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const bar = readBarForm(form);
    if (bar) approve(app, { bar }, form);
  });
  return form;
}

function showFieldErrors(form, errors) {
  for (const node of form.querySelectorAll(".field-error")) {
    const message = errors[node.dataset.for];
    node.textContent = message || "";
    node.hidden = !message;
  }
}

function readBarForm(form) {
  const value = (name) => form.elements[name].value.trim();
  const errors = {};
  if (!value("name")) errors.name = FIELD_ERROR_TEXT.MISSING;
  else if (value("name").length > 150) errors.name = "150자 이하로 입력하세요.";
  if (!value("address")) errors.address = FIELD_ERROR_TEXT.MISSING;
  else if (value("address").length > 500) errors.address = "500자 이하로 입력하세요.";
  if (value("phone").length > 30) errors.phone = "30자 이하로 입력하세요.";
  const coordinate = (name, limit) => {
    const raw = value(name);
    const number = Number(raw);
    if (!raw) errors[name] = FIELD_ERROR_TEXT.MISSING;
    else if (!Number.isFinite(number)) errors[name] = FIELD_ERROR_TEXT.FLOAT_PARSING;
    else if (Math.abs(number) > limit) errors[name] = `-${limit}~${limit} 사이여야 합니다.`;
    return number;
  };
  const latitude = coordinate("latitude", 90);
  const longitude = coordinate("longitude", 180);
  showFieldErrors(form, errors);
  if (Object.keys(errors).length) return null;
  return { name: value("name"), address: value("address"), latitude, longitude, phone: value("phone") || null };
}

function rejectForm(app) {
  const reason = el("textarea", { name: "reason", maxlength: "500", placeholder: "신청자에게 그대로 보입니다." });
  const error = el("div", { class: "message error", hidden: true });
  const form = el(
    "form",
    { class: "actions", novalidate: true },
    el("label", {}, "거절 사유"),
    reason,
    error,
    el("div", { class: "action-row" }, el("button", { type: "submit", class: "danger" }, "거절")),
  );
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = reason.value.trim();
    error.hidden = Boolean(text) && text.length <= 500;
    error.textContent = text ? "500자 이하로 입력하세요." : "거절 사유를 입력하세요.";
    if (error.hidden) reject(app, text);
  });
  return form;
}

function confirmApproval(app) {
  const result = app.businessVerification ? app.businessVerification.result : null;
  const lines = [`${barOf(app).name} 신청을 승인할까요?`];
  if (result === "unavailable") lines.push("", "국세청 검증을 하지 못한 신청입니다. 다시 확인하지 않고 승인합니다.");
  if (result === "not_matched") lines.push("", "사업자등록 정보가 국세청 정보와 맞지 않는 신청입니다.");
  if (app.businessStatus && app.businessStatus !== "active") {
    lines.push("", `사업자 상태가 ${label("businessStatus", app.businessStatus)}입니다.`);
  }
  return window.confirm(lines.join("\n"));
}

// Runs one action on the open application with the buttons disabled, then shows the result.
async function runAction(app, call, successText, onError) {
  if (state.busy) return;
  state.busy = true;
  for (const button of $("detail").querySelectorAll("button")) button.disabled = true;
  try {
    const updated = await call();
    state.detail = updated;
    state.notice = { kind: "ok", text: successText(updated) };
    replaceListItem(updated);
    renderDetail();
  } catch (error) {
    if (error.status === 401) return;
    if (onError && onError(error)) return;
    handleActionError(app, error);
  } finally {
    state.busy = false;
    for (const button of $("detail").querySelectorAll("button")) button.disabled = false;
  }
}

function handleActionError(app, error) {
  switch (error.code) {
    case "INVALID_APPLICATION_STATE":
      openDetail(app.applicationId, { kind: "error", text: "이미 처리된 신청입니다. 최신 상태를 불러왔습니다." });
      loadList(true);
      return;
    case "OWNER_APPLICATION_NOT_FOUND":
      closeDetail("신청을 찾을 수 없습니다. 목록을 다시 불러옵니다.");
      loadList(true);
      return;
    case "BAR_OWNER_EXISTS":
      setNotice("error", "이 업장에는 이미 업주가 있습니다. 같은 업장의 다른 신청이 먼저 승인되었으면 이 신청은 거절하세요.");
      return;
    case "BUSINESS_VERIFICATION_UNAVAILABLE":
      setNotice("error", "국세청 검증 서비스에 연결하지 못했습니다. 저장된 결과는 그대로입니다. 잠시 후 다시 시도하세요.");
      return;
    case "FORBIDDEN":
      showMessage("operator 권한이 없는 계정입니다.");
      return;
    default:
      setNotice("error", error.message);
  }
}

function setNotice(kind, text) {
  state.notice = { kind, text };
  renderDetail();
}

function verifyBusiness(app) {
  runAction(
    app,
    () => api("POST", `/api/owner-applications/${encodeURIComponent(app.applicationId)}/verify-business`),
    (updated) => `다시 확인했습니다: ${label("verification", updated.businessVerification && updated.businessVerification.result)}`,
  );
}

function approve(app, body, form) {
  if (!confirmApproval(app)) return;
  runAction(
    app,
    () => withUsersRow(() => api("POST", `/api/owner-applications/${encodeURIComponent(app.applicationId)}/approve`, body)),
    () =>
      app.menuPhotos.length
        ? "승인했습니다. 업장에 진행 중인 메뉴 등록이 없으면 메뉴판 사진으로 AI 분석을 시작합니다."
        : "승인했습니다. 메뉴판 사진이 없으므로 업주가 승인 뒤 메뉴를 올립니다.",
    (error) => {
      if (error.code !== "VALIDATION_FAILED" || !form) return false;
      const errors = {};
      for (const fieldError of error.fieldErrors) {
        const name = fieldError.path.replace(/^bar\.?/, "") || "name";
        errors[name] = FIELD_ERROR_TEXT[fieldError.code] || fieldError.message;
      }
      showFieldErrors(form, errors);
      return true;
    },
  );
}

function reject(app, reason) {
  if (!window.confirm(`${barOf(app).name} 신청을 거절할까요? 메뉴판 사진은 삭제됩니다.`)) return;
  runAction(
    app,
    () => withUsersRow(() => api("POST", `/api/owner-applications/${encodeURIComponent(app.applicationId)}/reject`, { reason })),
    () => "거절했습니다.",
  );
}

// ---------- wiring ----------

$("login-google").addEventListener("click", loginWithGoogle);
$("login-temp").addEventListener("click", loginTemporarily);
$("logout").addEventListener("click", async () => {
  await signOut();
  closeDetail();
  showLogin();
});
$("filters").addEventListener("change", (event) => {
  state.filters[event.target.name] = event.target.value;
  loadList(true);
});
$("refresh").addEventListener("click", () => loadList(true));
$("load-more").addEventListener("click", () => loadList(false));

start();
