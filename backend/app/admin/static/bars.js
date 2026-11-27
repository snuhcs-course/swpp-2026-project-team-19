// Operator bar management (API spec 3.4, 3.6, 3.7, 3.11.10): the "업장" tab of the dashboard. Lists bars,
// shows one, deactivates or reactivates it, and removes its owner. Bars are never deleted.
// Uses the helpers of app.js ($, el, api, withUsersRow, formatTime, fields, copyableId, showMessage).
// Data from the API is always put on the page as text (textContent), never as HTML.
"use strict";

const BAR_PAGE_SIZE = 20;
const BAR_DEFAULT_FILTERS = { status: "active", query: "" };
const BAR_LABELS = {
  status: { active: "활성", inactive: "비활성" },
  importStatus: { uploaded: "업로드됨", processing: "처리 중", ready_for_review: "검수 대기" },
};

const bars = {
  started: false,
  filters: { ...BAR_DEFAULT_FILTERS },
  items: [],
  nextCursor: null,
  listRequest: 0,
  listLoading: false,
  selectedId: null,
  detail: null,
  detailRequest: 0,
  busy: false,
  notice: null,
  // Bumped on sign-out, so a response that arrives afterwards is dropped instead of shown.
  session: 0,
};

function barLabel(group, value) {
  return value ? BAR_LABELS[group][value] || value : "-";
}

function barBadge(status) {
  return el("span", { class: `badge bar-${status}` }, barLabel("status", status));
}

function barPath(barId, suffix = "") {
  return `/api/bars/${encodeURIComponent(barId)}${suffix}`;
}

// Called by selectTab (checks.js) when the tab is opened.
function startBars() {
  if (bars.started) return;
  bars.started = true;
  loadBars(true);
}

// Bars hold owner emails, so nothing of them stays after sign-out (like clearDashboard).
function clearBars() {
  bars.listRequest++;
  bars.detailRequest++;
  bars.session++;
  setBarsBusy(false);
  bars.started = false;
  bars.filters = { ...BAR_DEFAULT_FILTERS };
  bars.items = [];
  bars.nextCursor = null;
  bars.listLoading = false;
  writeBarFilters();
  setBarListStatus("");
  $("bars-load-more").hidden = true;
  closeBarDetail();
}

// ---------- list (3.4) ----------

function writeBarFilters() {
  const form = $("bar-filters");
  form.elements.status.value = bars.filters.status;
  form.elements.query.value = bars.filters.query;
}

function setBarListStatus(text, retry) {
  $("bars-status").textContent = text;
  $("bars-retry").hidden = !retry;
  $("bars-retry").onclick = retry || null;
}

function barListQuery() {
  const params = new URLSearchParams({ status: bars.filters.status, limit: String(BAR_PAGE_SIZE) });
  if (bars.filters.query) params.set("query", bars.filters.query);
  if (bars.nextCursor) params.set("cursor", bars.nextCursor);
  return params;
}

async function loadBars(reset) {
  if (reset) {
    bars.items = [];
    bars.nextCursor = null;
    renderBarRows();
  }
  const request = ++bars.listRequest;
  bars.listLoading = true;
  $("bars-load-more").hidden = true;
  setBarListStatus("불러오는 중...");
  try {
    const page = await api("GET", `/api/bars?${barListQuery()}`);
    if (request !== bars.listRequest) return;
    bars.listLoading = false;
    bars.items = bars.items.concat(page.items);
    bars.nextCursor = page.nextCursor;
    renderBarRows();
    showBarListSummary();
  } catch (error) {
    if (request !== bars.listRequest) return;
    bars.listLoading = false;
    if (error.status === 401) return;
    if (error.code === "FORBIDDEN") {
      showMessage("operator 권한이 없는 계정입니다.");
      return;
    }
    const filtered = bars.nextCursor || JSON.stringify(bars.filters) !== JSON.stringify(BAR_DEFAULT_FILTERS);
    if (error.code === "VALIDATION_FAILED" && filtered) {
      // A search or cursor the server does not accept: start over from the defaults (3.4).
      bars.filters = { ...BAR_DEFAULT_FILTERS };
      writeBarFilters();
      setBarListStatus("검색 조건을 처음으로 되돌렸어요.");
      loadBars(true);
      return;
    }
    setBarListStatus(error.message, () => loadBars(false));
  }
}

function showBarListSummary() {
  setBarListStatus(
    bars.items.length
      ? `${bars.items.length}곳${bars.nextCursor ? " (더 있음)" : ""}`
      : bars.nextCursor
        ? "이 페이지의 업장이 모두 다른 상태로 바뀌었어요."
        : "조건에 맞는 업장이 없어요.",
  );
  $("bars-load-more").hidden = !bars.nextCursor;
}

function renderBarRows() {
  const rows = bars.items.map((item) =>
    el(
      "tr",
      {
        tabindex: "0",
        class: item.barId === bars.selectedId ? "selected" : null,
        onclick: () => selectBar(item.barId),
        onkeydown: (event) => {
          if (event.key === "Enter") selectBar(item.barId);
        },
      },
      el("td", {}, item.name),
      el("td", { class: "wrap" }, item.address),
      el("td", {}, barBadge(item.status)),
    ),
  );
  $("bar-rows").replaceChildren(...rows);
}

// Puts the bar's new state in the list, or drops it once it no longer matches the status filter. The cursor
// is keyed on the last row the server returned, so dropping rows here skips nothing on the next page.
function replaceBarItem(bar) {
  const index = bars.items.findIndex((item) => item.barId === bar.barId);
  if (index < 0) return;
  if (bars.filters.status === "all" || bar.status === bars.filters.status) {
    const { name, address, status } = bar;
    bars.items[index] = { ...bars.items[index], name, address, status };
  } else {
    bars.items.splice(index, 1);
  }
  renderBarRows();
  // A load in flight shows its own status when it finishes.
  if (!bars.listLoading) showBarListSummary();
}

// ---------- detail (3.6) ----------

// Another bar cannot be opened while an action runs, so its result never lands on the wrong one.
function selectBar(barId) {
  if (!bars.busy) openBarDetail(barId);
}

async function openBarDetail(barId, notice = null) {
  bars.selectedId = barId;
  bars.notice = notice;
  renderBarRows();
  const request = ++bars.detailRequest;
  if (!bars.detail || bars.detail.barId !== barId) {
    $("bar-detail").replaceChildren(el("p", { class: "placeholder" }, "불러오는 중..."));
  }
  try {
    const bar = await api("GET", barPath(barId));
    if (request !== bars.detailRequest) return;
    bars.detail = bar;
    replaceBarItem(bar);
    renderBarDetail();
  } catch (error) {
    if (request !== bars.detailRequest || error.status === 401) return;
    if (error.code === "BAR_NOT_FOUND") {
      closeBarDetail("업장을 찾을 수 없어요. 목록을 다시 불러옵니다.");
      loadBars(true);
      return;
    }
    if (error.code === "FORBIDDEN") {
      showMessage("operator 권한이 없는 계정입니다.");
      return;
    }
    $("bar-detail").replaceChildren(
      el("p", { class: "notice error" }, error.message),
      el("button", { type: "button", onclick: () => openBarDetail(barId) }, "다시 시도"),
    );
  }
}

function closeBarDetail(message) {
  bars.selectedId = null;
  bars.detail = null;
  bars.notice = null;
  renderBarRows();
  $("bar-detail").replaceChildren(el("p", { class: "placeholder" }, message || "목록에서 업장을 고르세요."));
}

function ownerText(owner) {
  return [owner.displayName, owner.email].filter(Boolean).join(" / ") || "-";
}

function renderBarDetail() {
  const bar = bars.detail;
  if (!bar) return;
  const children = [el("h2", {}, bar.name), el("div", { class: "action-row" }, barBadge(bar.status))];
  if (bars.notice) children.push(el("p", { class: `notice ${bars.notice.kind}`, role: "status" }, bars.notice.text));

  children.push(el("h3", {}, "업장 정보"));
  children.push(
    fields([
      ["업장 ID", copyableId(bar.barId)],
      ["주소", bar.address],
      ["매장 전화", bar.phone],
      ["고객에게 보이는 전화", bar.customerPhone],
      ["상태", barLabel("status", bar.status)],
      ["등록", formatTime(bar.createdAt)],
      ["수정", formatTime(bar.updatedAt)],
    ]),
  );

  children.push(el("h3", {}, "현재 업주"));
  children.push(
    bar.owner
      ? fields([
          ["업주", ownerText(bar.owner)],
          ["사용자 ID", copyableId(bar.owner.userId)],
          ["승인", formatTime(bar.owner.ownerSince)],
        ])
      : el("p", { class: "placeholder" }, "업주 없음"),
  );

  children.push(el("h3", {}, "진행 중인 메뉴 등록 작업"));
  children.push(
    bar.activeMenuImport
      ? fields([
          ["상태", barLabel("importStatus", bar.activeMenuImport.status)],
          ["작업 ID", copyableId(bar.activeMenuImport.menuImportId)],
        ])
      : el("p", { class: "placeholder" }, "없음"),
  );

  children.push(el("h3", {}, "관리"));
  const active = bar.status === "active";
  const actions = el(
    "div",
    { class: "action-row" },
    active
      ? el("button", { type: "button", class: "danger", onclick: () => setBarStatus(bar, "inactive") }, "비활성화")
      : el("button", { type: "button", onclick: () => setBarStatus(bar, "active") }, "다시 활성화"),
    bar.owner
      ? el("button", { type: "button", class: "danger", onclick: () => removeBarOwner(bar) }, "업주 해제")
      : null,
  );
  children.push(actions);
  children.push(
    el(
      "p",
      { class: "hint" },
      "업장은 지우지 않아요. 비활성 업장은 고객 검색과 고객용 상세에서 빠지고 새 메뉴 등록을 받지 않으며, 업주는 계속 관리할 수 있어요. 업주를 해제해도 업장 상태는 그대로예요.",
    ),
  );
  $("bar-detail").replaceChildren(...children);
}

// ---------- actions (3.7, 3.11.10) ----------

function setBarsBusy(busy) {
  bars.busy = busy;
  $("bar-rows").classList.toggle("busy", busy);
  for (const control of $("bar-filters").elements) control.disabled = busy;
  $("bars-load-more").disabled = busy;
  $("bars-retry").disabled = busy;
  for (const button of $("bar-detail").querySelectorAll("button")) button.disabled = busy;
}

// Runs one action on the open bar with the controls disabled. `call` returns the notice to show.
async function runBarAction(bar, call) {
  if (bars.busy) return;
  const session = bars.session;
  setBarsBusy(true);
  // The detail may have changed meanwhile (sign-out), so the result goes only on the same bar.
  const stillOpen = () => session === bars.session && bars.selectedId === bar.barId;
  try {
    const notice = await call(stillOpen);
    if (stillOpen() && notice) {
      bars.notice = notice;
      renderBarDetail();
    }
  } catch (error) {
    if (error.status === 401 || !stillOpen()) return;
    handleBarActionError(bar, error);
  } finally {
    if (session === bars.session) setBarsBusy(false);
  }
}

function setBarStatus(bar, status) {
  if (status === "inactive") {
    const ok = window.confirm(
      `${bar.name}을(를) 비활성화할까요?\n\n고객 검색에서 빠지고 새 메뉴 등록을 받지 않아요. 업장과 메뉴 기록은 지우지 않으며, 다시 활성화할 수 있어요.`,
    );
    if (!ok) return;
  }
  runBarAction(bar, async (stillOpen) => {
    const updated = await api("PATCH", barPath(bar.barId), { status });
    // A list request still in flight may have read the bar before this change; load again.
    if (bars.listLoading) loadBars(true);
    else replaceBarItem(updated);
    if (!stillOpen()) return null;
    bars.detail = updated;
    return { kind: "ok", text: status === "inactive" ? "비활성화했어요." : "다시 활성화했어요." };
  });
}

function removeBarOwner(bar) {
  const ok = window.confirm(
    `${bar.name}의 업주(${ownerText(bar.owner)})를 해제할까요?\n\n다음 요청부터 이 업장을 관리할 수 없어요. 업주 신청 기록은 남고, 해제된 사람은 다시 신청할 수 있어요. 업장 상태는 바뀌지 않아요.`,
  );
  if (!ok) return;
  runBarAction(bar, async (stillOpen) => {
    // Records the operator who removed the owner, who needs a users row (3.11.10).
    await withUsersRow(() => api("DELETE", barPath(bar.barId, "/owner")));
    if (stillOpen()) await openBarDetail(bar.barId, { kind: "ok", text: "업주를 해제했어요." });
    return null;
  });
}

function handleBarActionError(bar, error) {
  switch (error.code) {
    case "BAR_OWNER_NOT_FOUND":
      openBarDetail(bar.barId, { kind: "warn", text: "이 업장에는 이미 업주가 없어요. 최신 상태를 불러왔어요." });
      return;
    case "BAR_NOT_FOUND":
      closeBarDetail("업장을 찾을 수 없어요. 목록을 다시 불러옵니다.");
      loadBars(true);
      return;
    case "FORBIDDEN":
      showMessage("operator 권한이 없는 계정입니다.");
      return;
    case "VALIDATION_FAILED":
      bars.notice = { kind: "error", text: error.fieldErrors.map((e) => e.message).join(" ") || error.message };
      renderBarDetail();
      return;
    default:
      bars.notice = { kind: "error", text: error.message };
      renderBarDetail();
  }
}

// ---------- wiring ----------

$("bar-filters").addEventListener("change", (event) => {
  if (event.target.name !== "status") return;
  bars.filters.status = event.target.value;
  loadBars(true);
});
$("bar-filters").addEventListener("submit", (event) => {
  event.preventDefault();
  bars.filters.query = event.target.elements.query.value.trim();
  loadBars(true);
});
$("bars-refresh").addEventListener("click", () => loadBars(true));
$("bars-load-more").addEventListener("click", () => loadBars(false));
