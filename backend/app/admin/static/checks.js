// Operator menu item checks (API spec 3.18.2, 3.18.3): the "메뉴 확인" tab of the dashboard.
// Uses the helpers of app.js ($, el, api, formatTime, fields, showMessage, FIELD_ERROR_TEXT).
// Data from the API is always put on the page as text (textContent), never as HTML.
"use strict";

const CHECK_PAGE_SIZE = 50;

const CHECK_LABELS = {
  status: { open: "처리 전", resolved: "처리됨", dismissed: "닫힘" },
  reason: {
    unlinked: "상품 없음",
    relinked_by_name: "이름 고쳐 다른 상품에 연결",
    unlinked_by_name: "이름 고쳐 연결 풀림",
    attribute_conflict: "연수나 에디션 다름",
    price_conflict: "가격 충돌",
  },
  resolution: {
    link_existing: "기존 상품에 연결",
    create_and_link: "새 상품 등록 후 연결",
    keep: "지금 연결 유지",
    mark_as_other: "위스키 아닌 메뉴로 바꿈",
  },
  kind: { whisky: "위스키", other: "위스키 아닌 메뉴" },
};

const RESOLVED_TEXT = {
  link_existing: "상품에 연결했습니다. 이제 고객 검색에 나옵니다.",
  create_and_link: "새 상품을 등록하고 연결했습니다. 이제 고객 검색에 나옵니다.",
  keep: "지금 연결을 유지하고 확인을 닫았습니다.",
  mark_as_other: "위스키 아닌 메뉴로 바꾸고 확인을 닫았습니다.",
};

const checks = {
  started: false,
  filters: { status: "open", barId: "", barName: "" },
  items: [],
  nextCursor: null,
  listRequest: 0,
  listLoading: false,
  selectedId: null,
  pages: 0,
  busy: false,
  imagesRefreshed: false,
  // Bumped on sign-out, so a response that arrives afterwards is dropped instead of shown.
  session: 0,
  // checkId -> the product a link in this session resolved it to; see movedLink().
  resolvedProducts: new Map(),
};

function checkLabel(group, value) {
  return value ? CHECK_LABELS[group][value] || value : "-";
}

function formatPrice(value) {
  return `${Number(value).toLocaleString("ko-KR")}원`;
}

function optionText(option) {
  return [option.optionLabel, option.pourMl ? `${option.pourMl}ml` : null, formatPrice(option.priceKrw)]
    .filter(Boolean)
    .join(" ");
}

function productText(product) {
  if (!product) return "없음";
  const extra = [product.ageYears !== null ? `${product.ageYears}년` : null, product.editionName].filter(Boolean);
  return `${product.brandName} / ${product.displayName}${extra.length ? ` (${extra.join(", ")})` : ""}`;
}

// ---------- tabs ----------

function selectTab(name) {
  const onChecks = name === "checks";
  $("panel-applications").hidden = onChecks;
  $("panel-checks").hidden = !onChecks;
  $("tab-applications").setAttribute("aria-selected", String(!onChecks));
  $("tab-checks").setAttribute("aria-selected", String(onChecks));
  history.replaceState(null, "", onChecks ? "#checks" : location.pathname);
  if (onChecks && !checks.started) {
    checks.started = true;
    loadChecks(true);
  }
}

// Checks hold signed photo URLs, so nothing of them stays after sign-out (like clearDashboard).
function clearChecks() {
  checks.listRequest++;
  checks.session++;
  checks.resolvedProducts.clear();
  // A resolve still in flight is dropped (resolveCheck), so its controls are enabled here.
  setCheckBusy(false);
  checks.started = false;
  checks.filters = { status: "open", barId: "", barName: "" };
  checks.items = [];
  checks.nextCursor = null;
  checks.listLoading = false;
  $("check-filters").elements.status.value = "open";
  $("check-filters").elements.barQuery.value = "";
  $("check-bar-results").replaceChildren();
  renderBarFilter();
  setCheckListStatus("");
  $("checks-load-more").hidden = true;
  closeCheckDetail();
}

// ---------- list (3.18.2) ----------

function setCheckListStatus(text, retry) {
  $("checks-status").textContent = text;
  $("checks-retry").hidden = !retry;
  $("checks-retry").onclick = retry || null;
}

// `keepDetail` leaves the detail pane as it is, e.g. showing a check just resolved that left the list.
// `keepPages` loads again as many pages as are shown, so a check from a later page stays in the list.
async function loadChecks(reset, { keepDetail = false, keepPages = false } = {}) {
  const pages = reset && keepPages ? Math.max(1, checks.pages) : 1;
  if (reset) {
    checks.items = [];
    checks.nextCursor = null;
    checks.pages = 0;
    renderCheckRows();
  }
  const request = ++checks.listRequest;
  checks.listLoading = true;
  setCheckListStatus("불러오는 중...");
  $("checks-load-more").hidden = true;
  try {
    for (let loaded = 0; loaded < pages; loaded++) {
      const params = new URLSearchParams({ status: checks.filters.status, limit: String(CHECK_PAGE_SIZE) });
      if (checks.filters.barId) params.set("barId", checks.filters.barId);
      if (checks.nextCursor) params.set("cursor", checks.nextCursor);
      const page = await api("GET", `/api/menu-item-checks?${params}`);
      if (request !== checks.listRequest) return;
      const known = new Set(checks.items.map((check) => check.checkId));
      checks.items = [...checks.items, ...page.items.filter((check) => !known.has(check.checkId))];
      checks.nextCursor = page.nextCursor;
      checks.pages++;
      if (!checks.nextCursor) break;
    }
    checks.listLoading = false;
    renderCheckRows();
    showCheckListSummary();
    if (reset && checks.selectedId && !keepDetail) {
      // A fresh load also hands out fresh photo URLs; a check that left the list closes.
      const fresh = checks.items.find((check) => check.checkId === checks.selectedId);
      if (fresh) renderCheckDetail(fresh);
      else closeCheckDetail();
    }
  } catch (error) {
    if (request !== checks.listRequest) return;
    checks.listLoading = false;
    if (error.status === 401) return;
    if (error.code === "VALIDATION_FAILED" && checks.nextCursor) {
      // INVALID_CURSOR: start over from the first page (3.18.2).
      loadChecks(true);
      return;
    }
    if (error.code === "FORBIDDEN") {
      showMessage("operator 권한이 없는 계정입니다.");
      return;
    }
    setCheckListStatus(error.message, () => loadChecks(reset, { keepDetail, keepPages }));
  }
}

function showCheckListSummary() {
  setCheckListStatus(
    checks.items.length
      ? `${checks.items.length}건${checks.nextCursor ? " (더 있음)" : ""}`
      : checks.nextCursor
        ? "이 페이지의 확인을 모두 처리했습니다."
        : "조건에 맞는 확인이 없습니다.",
  );
  $("checks-load-more").hidden = !checks.nextCursor;
}

function reasonBadges(check) {
  const reasons = [...new Set(check.reasons.map((reason) => reason.reason))];
  return reasons.map((reason) => el("span", { class: `badge ${reason}` }, checkLabel("reason", reason)));
}

function renderCheckRows() {
  const closed = checks.filters.status !== "open";
  $("checks-time-header").textContent = closed ? "닫힌 시각" : "생긴 시각";
  const rows = checks.items.map((check) =>
    el(
      "tr",
      {
        tabindex: "0",
        class: check.checkId === checks.selectedId ? "selected" : null,
        onclick: () => selectCheck(check.checkId),
        onkeydown: (event) => {
          if (event.key === "Enter") selectCheck(check.checkId);
        },
      },
      el("td", {}, formatTime(closed ? check.resolvedAt : check.createdAt)),
      el(
        "td",
        {},
        check.bar.name,
        check.bar.status === "inactive" ? [" ", el("span", { class: "badge warning" }, "비활성")] : null,
      ),
      el("td", {}, check.item.displayName),
      el("td", { class: "badges" }, reasonBadges(check)),
      el("td", {}, movedLink(check) ? resolvedProductText(check) : check.item.product ? check.item.product.displayName : "없음"),
      el(
        "td",
        {},
        check.status === "resolved" ? checkLabel("resolution", check.resolution) : checkLabel("status", check.status),
      ),
    ),
  );
  $("check-rows").replaceChildren(...rows);
}

// Puts the resolved check in the list, or drops it once it no longer matches the status filter.
// The cursor is keyed on the last row the server returned, so dropping rows skips nothing.
function replaceCheck(check) {
  const index = checks.items.findIndex((item) => item.checkId === check.checkId);
  if (index < 0) return;
  if (check.status === checks.filters.status) checks.items[index] = check;
  else checks.items.splice(index, 1);
  renderCheckRows();
  if (!checks.listLoading) showCheckListSummary();
}

// ---------- bar filter ----------

function renderBarFilter() {
  const box = $("check-bar-filter");
  box.hidden = !checks.filters.barId;
  box.replaceChildren(
    el("span", {}, `업장: ${checks.filters.barName}`),
    el("button", { type: "button", class: "link", onclick: () => setBarFilter("", "") }, "모든 업장 보기"),
  );
}

function setBarFilter(barId, barName) {
  if (checks.busy) return;
  checks.filters.barId = barId;
  checks.filters.barName = barName;
  $("check-bar-results").replaceChildren();
  renderBarFilter();
  loadChecks(true);
}

// Bar-name search finds active bars only (3.15); an inactive bar's checks are filtered from their detail.
async function findBars(query) {
  const results = $("check-bar-results");
  if (!query.trim()) {
    results.replaceChildren(el("p", { class: "hint" }, "업장 이름이나 주소를 입력하세요."));
    return;
  }
  results.replaceChildren(el("p", { class: "hint" }, "찾는 중..."));
  const session = checks.session;
  try {
    const found = await api("GET", `/api/search/bar-names?${new URLSearchParams({ query: query.trim(), limit: "10" })}`);
    if (session !== checks.session) return;
    results.replaceChildren(
      ...(found.items.length
        ? found.items.map((bar) =>
            el(
              "button",
              { type: "button", class: "candidate", onclick: () => setBarFilter(bar.barId, bar.name) },
              `${bar.name} (${bar.address})`,
            ),
          )
        : [el("p", { class: "hint" }, "맞는 업장이 없습니다.")]),
    );
  } catch (error) {
    if (error.status !== 401 && session === checks.session) {
      results.replaceChildren(el("p", { class: "error-text" }, error.message));
    }
  }
}

// ---------- detail ----------

// Another check cannot be opened while a resolve runs, so its result never lands on the wrong one.
function selectCheck(checkId) {
  if (checks.busy) return;
  const check = checks.items.find((item) => item.checkId === checkId);
  if (!check) return;
  if (checks.selectedId !== checkId) checks.imagesRefreshed = false;
  checks.selectedId = checkId;
  renderCheckRows();
  renderCheckDetail(check);
}

function closeCheckDetail(message) {
  checks.selectedId = null;
  renderCheckRows();
  $("check-detail").replaceChildren(el("p", { class: "placeholder" }, message || "목록에서 확인할 항목을 고르세요."));
}

function setCheckNotice(kind, ...content) {
  const box = $("check-notice");
  if (!box) return;
  box.replaceChildren(...(content.length ? [el("div", { class: `notice ${kind}` }, ...content)] : []));
  box.scrollIntoView({ block: "nearest" });
}

// A link can move the line to another item of the bar while the check stays on its own item (3.18.3),
// so the product the check was resolved to can differ from the item's product.
function movedLink(check) {
  return (
    check.status === "resolved" &&
    check.resolvedProductId !== null &&
    (!check.item.product || check.item.product.productId !== check.resolvedProductId)
  );
}

// The answer has only the product's id; its name is known only for a link made on this page.
function resolvedProductText(check) {
  return checks.resolvedProducts.get(check.checkId) || "다른 항목으로 옮겨 연결함";
}

function renderCheckDetail(check) {
  const open = check.status === "open";
  const item = check.item;
  const children = [
    el("h2", {}, item.displayName),
    el(
      "div",
      { class: "action-row" },
      el("span", { class: `badge ${check.status}` }, checkLabel("status", check.status)),
      check.bar.name,
      check.bar.status === "inactive" ? el("span", { class: "badge warning" }, "비활성 업장") : null,
      checks.filters.barId === check.bar.barId
        ? null
        : el(
            "button",
            { type: "button", class: "link", onclick: () => setBarFilter(check.bar.barId, check.bar.name) },
            "이 업장만 보기",
          ),
    ),
    el("div", { id: "check-notice" }),
    el("h3", {}, "메뉴 항목"),
    fields([
      ["종류", checkLabel("kind", item.kind)],
      ["연결 상품", productText(item.product)],
      ...(movedLink(check) ? [["처리 결과 상품", resolvedProductText(check)]] : []),
      [
        "메뉴판",
        item.onBoard
          ? item.soldOut
            ? "있음 (품절)"
            : "있음"
          : movedLink(check)
            ? "없음 (줄이 다른 항목으로 옮겨짐)"
            : "없음 (메뉴판에서 빠짐)",
      ],
      ["현재 옵션", item.options.length ? item.options.map(optionText).join(", ") : "-"],
      ["생긴 시각", formatTime(check.createdAt)],
      ...(open
        ? []
        : [
            ["닫힌 시각", formatTime(check.resolvedAt)],
            ["처리 방식", check.status === "resolved" ? checkLabel("resolution", check.resolution) : "메뉴판에서 빠져 닫힘"],
          ]),
    ]),
    el("h3", {}, `사유 (${check.reasons.length})`),
    ...check.reasons.map((reason) => renderReason(check, reason)),
  ];
  if (check.discardedOptions.length) {
    children.push(el("h3", {}, "합치면서 버린 가격"));
    children.push(
      el(
        "ul",
        { class: "plain-list" },
        check.discardedOptions.map((option) => el("li", {}, `${option.displayName}: ${optionText(option)}`)),
      ),
    );
    children.push(el("p", { class: "hint" }, "메뉴판에 남은 가격은 위의 현재 옵션입니다."));
  }
  if (open) children.push(renderCheckActions(check));
  $("check-detail").replaceChildren(...children);
}

function renderReason(check, reason) {
  const source = reason.source;
  const box = el(
    "div",
    { class: "reason" },
    el(
      "div",
      { class: "action-row" },
      el("span", { class: `badge ${reason.reason}` }, checkLabel("reason", reason.reason)),
      el("span", { class: "hint" }, formatTime(reason.addedAt)),
    ),
  );
  if (!source) {
    box.append(el("p", { class: "hint" }, "업주의 직접 추가나 직접 수정으로 생긴 사유입니다. 검수 사진이 없습니다."));
    return box;
  }
  box.append(lineCrop(source, check));
  box.append(
    fields([
      ["원문", source.rawText],
      ["읽은 이름", source.extractedProductName],
      ["읽은 브랜드", source.extractedBrandName],
      ["읽은 연수", source.extractedAgeYears !== null ? `${source.extractedAgeYears}년` : null],
      ["읽은 에디션", source.extractedEditionName],
    ]),
  );
  return box;
}

// The line cut out of the photo by sourceBox (0-1000 of the photo's width and height, 5.4); the whole
// photo when there is no box. Clicking opens the whole photo.
function lineCrop(source, check) {
  const link = el("a", {
    href: source.imageUrl,
    target: "_blank",
    rel: "noopener noreferrer",
    class: source.sourceBox ? "line-crop" : "line-crop whole",
    title: "사진 전체 보기",
  });
  const img = el("img", {
    src: source.imageUrl,
    alt: `메뉴판 사진: ${source.rawText}`,
    loading: "lazy",
    // A signed URL may have expired; a fresh list hands out new ones (3.18.2). Once per opening.
    onerror: () => {
      if (checks.imagesRefreshed || checks.selectedId !== check.checkId) return;
      checks.imagesRefreshed = true;
      loadChecks(true, { keepPages: true });
    },
  });
  link.append(img);
  const box = source.sourceBox;
  if (!box) return link;
  // A little margin so the crop does not cut the letters.
  const pad = 6;
  const x0 = Math.max(0, box[0] - pad);
  const y0 = Math.max(0, box[1] - pad);
  const width = Math.max(1, Math.min(1000, box[2] + pad) - x0);
  const height = Math.max(1, Math.min(1000, box[3] + pad) - y0);
  img.addEventListener("load", () => {
    link.style.aspectRatio = `${width * img.naturalWidth} / ${height * img.naturalHeight}`;
    img.style.width = `${100000 / width}%`;
    img.style.height = `${100000 / height}%`;
    img.style.left = `${(-x0 * 100) / width}%`;
    img.style.top = `${(-y0 * 100) / height}%`;
    link.classList.add("cropped");
  });
  return link;
}

// ---------- resolve (3.18.3) ----------

function firstSource(check) {
  const reason = check.reasons.find((r) => r.source);
  return reason ? reason.source : null;
}

function renderCheckActions(check) {
  // A fieldset disables every control while a resolve runs and keeps each control's own state.
  const box = el("fieldset", { id: "check-actions", class: "plain actions" }, el("h3", {}, "처리"));
  if (check.bar.status === "inactive") {
    box.append(el("p", { class: "notice warn" }, "비활성 업장의 확인은 처리할 수 없습니다. 업장을 다시 활성화한 뒤 처리하세요."));
    return box;
  }
  if (!check.item.onBoard) {
    box.append(el("p", { class: "notice warn" }, "메뉴판에 없는 항목입니다. 목록을 새로고침하세요."));
    return box;
  }
  if (check.reasons.some((r) => r.reason === "price_conflict")) {
    box.append(
      el(
        "p",
        { class: "notice warn" },
        "버린 가격이 맞으면 먼저 메뉴 직접 수정으로 옵션을 고친 뒤(이름은 그대로) 이 확인을 처리하세요. " +
          (check.item.product ? "가격만 확인했으면 '지금 연결 유지'로 닫습니다." : "상품 없는 항목은 상품에 연결해 닫습니다."),
      ),
    );
  }
  box.append(
    check.item.product
      ? el(
          "div",
          { class: "action-row" },
          el("button", { type: "button", onclick: () => confirmAndResolve(check, { resolution: "keep" }) }, "지금 연결 유지"),
          el("span", { class: "hint" }, "연결된 상품이 맞으면 메뉴는 그대로 두고 확인만 닫습니다."),
        )
      : el(
          "div",
          { class: "action-row" },
          el(
            "button",
            { type: "button", class: "secondary", onclick: () => confirmAndResolve(check, { resolution: "mark_as_other" }) },
            "위스키 아닌 메뉴로 바꾸기",
          ),
          el("span", { class: "hint" }, "칵테일이나 안주처럼 카탈로그에 넣지 않을 메뉴입니다."),
        ),
  );
  box.append(el("h3", {}, check.item.product ? "다른 상품으로 연결 바꾸기" : "기존 상품에 연결"), linkForm(check));
  box.append(el("h3", {}, "새 상품 등록 후 연결"), createForm(check));
  return box;
}

function confirmAndResolve(check, body) {
  const question =
    body.resolution === "keep"
      ? `'${check.item.displayName}'의 지금 연결(${productText(check.item.product)})이 맞다고 확인할까요?`
      : `'${check.item.displayName}'을 위스키 아닌 메뉴로 바꿀까요? 고객 검색에는 계속 나오지 않습니다.`;
  if (window.confirm(question)) resolveCheck(check, body, null);
}

function formRow(labelText, control, hint) {
  const id = `check-field-${control.name.replace(/[^\w]/g, "-")}`;
  control.id = id;
  const row = [el("label", { for: id }, labelText), control];
  if (hint) row.push(el("span", { class: "hint field-hint" }, hint));
  return row;
}

// The board's spelling, offered as an alias of the product (3.18.3); an empty text adds none.
function aliasRows(prefix, text) {
  const hangul = /[가-힣]/.test(text);
  return [
    ...formRow(
      "별칭",
      el("input", { name: `${prefix}[0].aliasText`, value: text, maxlength: "200" }),
      "이 상품의 정상 표기일 때만 남겨 두세요. 비우면 별칭을 넣지 않습니다.",
    ),
    ...formRow(
      "별칭 언어",
      el(
        "select",
        { name: `${prefix}[0].languageCode` },
        el("option", { value: "ko", selected: hangul }, "한국어 (ko)"),
        el("option", { value: "en", selected: !hangul }, "영어 (en)"),
        el("option", { value: "" }, "정하지 않음"),
      ),
    ),
    el("span", {}),
    el(
      "label",
      { class: "check" },
      el("input", { type: "checkbox", name: `${prefix}[0].isSearchable`, checked: true }),
      " 손님 검색에 사용 (오타라면 끄세요)",
    ),
  ];
}

function readAliases(form, prefix) {
  const text = form.elements[`${prefix}[0].aliasText`].value.trim();
  if (!text) return [];
  return [
    {
      aliasText: text,
      languageCode: form.elements[`${prefix}[0].languageCode`].value || null,
      isSearchable: form.elements[`${prefix}[0].isSearchable`].checked,
    },
  ];
}

function clearCheckFieldErrors(form) {
  for (const node of form.querySelectorAll(".field-error")) node.remove();
}

// Puts each error under its field; errors without a field on this form are returned for the notice.
function showCheckFieldErrors(form, fieldErrors) {
  clearCheckFieldErrors(form);
  const rest = [];
  for (const fieldError of fieldErrors) {
    const control = form && fieldError.path ? form.elements[fieldError.path] : null;
    const text = FIELD_ERROR_TEXT[fieldError.code] || fieldError.message;
    if (control && control.id) {
      // After the control's hint, if any, so the grid keeps label and control on one row.
      let anchor = control;
      if (anchor.nextElementSibling && anchor.nextElementSibling.classList.contains("field-hint")) {
        anchor = anchor.nextElementSibling;
      }
      anchor.after(el("p", { class: "field-error" }, text));
    } else {
      rest.push(text);
    }
  }
  return rest;
}

function productCandidate(product, onPick) {
  const extra = [
    product.ageYears !== null ? `${product.ageYears}년` : null,
    product.editionName,
    product.abv !== null ? `${product.abv}%` : null,
  ].filter(Boolean);
  return el(
    "button",
    { type: "button", class: "candidate", disabled: !product.isActive, onclick: () => onPick(product) },
    `${product.brandName} / ${product.displayName}${extra.length ? ` (${extra.join(", ")})` : ""}`,
    product.isActive ? null : [" ", el("span", { class: "badge warning" }, "비활성")],
    product.matchedAlias !== product.displayName ? el("span", { class: "hint" }, ` 별칭: ${product.matchedAlias}`) : null,
  );
}

function linkForm(check) {
  const source = firstSource(check);
  let selected = null;
  const results = el("div", { class: "candidates" });
  const chosen = el("p", { class: "hint" }, "검색해서 연결할 상품을 고르세요.");
  const submit = el("button", { type: "submit", disabled: true }, "이 상품에 연결");

  const search = el(
    "form",
    {
      class: "action-row",
      onsubmit: (event) => {
        event.preventDefault();
        searchProducts(search.elements.query.value, results, (product) => {
          selected = product;
          chosen.replaceChildren("연결할 상품: ", el("strong", {}, productText(product)));
          submit.disabled = false;
          results.replaceChildren();
        });
      },
    },
    el("input", {
      type: "search",
      name: "query",
      value: (source && source.extractedProductName) || check.item.displayName,
      maxlength: "100",
      "aria-label": "상품 이름이나 별칭",
    }),
    el("button", { type: "submit", class: "secondary" }, "상품 검색"),
  );

  const form = el(
    "form",
    {
      class: "form-grid",
      onsubmit: (event) => {
        event.preventDefault();
        if (!selected) return;
        clearCheckFieldErrors(form);
        const body = { resolution: "link_existing", productId: selected.productId, aliasesToAdd: readAliases(form, "aliasesToAdd") };
        if (window.confirm(`'${check.item.displayName}'을 ${productText(selected)}에 연결할까요?`)) {
          resolveCheck(check, body, form, productText(selected));
        }
      },
    },
    ...aliasRows("aliasesToAdd", check.item.displayName),
    el("span", {}),
    el("div", { class: "action-row" }, submit),
  );
  return el("div", { class: "check-form" }, search, results, chosen, form);
}

async function searchProducts(query, results, onPick) {
  if (!query.trim()) {
    results.replaceChildren(el("p", { class: "hint" }, "상품 이름이나 별칭을 입력하세요."));
    return;
  }
  results.replaceChildren(el("p", { class: "hint" }, "찾는 중..."));
  const params = new URLSearchParams({ query: query.trim(), includeInactive: "true", limit: "20" });
  try {
    const found = await api("GET", `/api/catalog/products?${params}`);
    results.replaceChildren(
      ...(found.items.length
        ? found.items.map((product) => productCandidate(product, onPick))
        : [el("p", { class: "hint" }, "맞는 상품이 없습니다. 아래에서 새 상품으로 등록하세요.")]),
    );
  } catch (error) {
    if (error.status !== 401) results.replaceChildren(el("p", { class: "error-text" }, error.message));
  }
}

function createForm(check) {
  const source = firstSource(check);
  const brandResults = el("div", { class: "candidates" });
  const brandChosen = el("span", { class: "hint" }, "브랜드를 검색해 고르세요.");
  const brandId = el("input", { type: "hidden", name: "brand.brandId" });

  const form = el("form", { class: "form-grid" });
  const brandType = (value, text, checked) =>
    el("label", { class: "check" }, el("input", { type: "radio", name: "brandType", value, checked }), ` ${text}`);
  const existingBrand = el(
    "div",
    { class: "geocode" },
    el(
      "div",
      { class: "action-row" },
      el("input", {
        type: "search",
        name: "brandQuery",
        value: (source && source.extractedBrandName) || "",
        maxlength: "100",
        "aria-label": "브랜드 이름이나 별칭",
      }),
      el(
        "button",
        {
          type: "button",
          class: "secondary",
          onclick: () =>
            searchBrands(form.elements.brandQuery.value, brandResults, (brand) => pickBrand(brand.brandId, brand.canonicalName)),
        },
        "브랜드 검색",
      ),
    ),
    brandResults,
    brandChosen,
    brandId,
  );
  const pickBrand = (id, name) => {
    form.elements.brandType.value = "existing";
    brandId.value = id;
    form.brandName = name;
    brandChosen.replaceChildren("브랜드: ", el("strong", {}, name));
    brandResults.replaceChildren();
    toggleBrand();
  };
  const newBrand = el("input", {
    name: "brand.canonicalName",
    value: (source && source.extractedBrandName) || "",
    maxlength: "120",
  });
  const newBrandRow = formRow("새 브랜드 이름", newBrand);
  const existingBrandRow = [el("span", {}), existingBrand];
  const toggleBrand = () => {
    const isNew = form.elements.brandType.value === "new";
    for (const node of newBrandRow) node.hidden = !isNew;
    for (const node of existingBrandRow) node.hidden = isNew;
  };

  form.append(
    el("span", {}, "브랜드"),
    el("div", { class: "action-row", onchange: toggleBrand }, brandType("existing", "기존 브랜드", true), brandType("new", "새 브랜드", false)),
    ...existingBrandRow,
    ...newBrandRow,
    ...formRow(
      "상품 이름",
      el("input", { name: "product.displayName", value: (source && source.extractedProductName) || check.item.displayName, maxlength: "200" }),
      "카탈로그의 정식 이름입니다. 별칭으로도 들어갑니다.",
    ),
    ...formRow(
      "연수",
      el("input", { name: "product.ageYears", type: "number", min: "0", max: "200", step: "1", value: source && source.extractedAgeYears !== null ? String(source.extractedAgeYears) : "" }),
    ),
    ...formRow("에디션", el("input", { name: "product.editionName", value: (source && source.extractedEditionName) || "", maxlength: "150" })),
    ...formRow("도수 (%)", el("input", { name: "product.abv", type: "number", min: "0", max: "100", step: "0.1" })),
    ...aliasRows("aliases", check.item.displayName),
    el("span", {}),
    el("div", { class: "action-row" }, el("button", { type: "submit" }, "등록하고 연결")),
  );
  form.pickBrand = pickBrand;
  toggleBrand();

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const body = readCreateForm(form);
    if (!body) return;
    if (window.confirm(`'${body.product.displayName}'을 카탈로그에 등록하고 '${check.item.displayName}'에 연결할까요?`)) {
      const brandName = body.brand.type === "new" ? body.brand.canonicalName : form.brandName;
      resolveCheck(check, body, form, productText({ ...body.product, brandName }));
    }
  });
  return el("div", { class: "check-form" }, form);
}

// The create_and_link body, or null after showing what is missing (the server checks the rest).
function readCreateForm(form) {
  const value = (name) => form.elements[name].value.trim();
  const errors = [];
  const isNew = form.elements.brandType.value === "new";
  if (isNew && !value("brand.canonicalName")) errors.push({ path: "brand.canonicalName", code: "MISSING" });
  if (!isNew && !value("brand.brandId")) errors.push({ path: "brand.brandId", message: "브랜드를 검색해 고르세요." });
  if (!value("product.displayName")) errors.push({ path: "product.displayName", code: "MISSING" });
  const age = value("product.ageYears");
  const abv = value("product.abv");
  if (age && !/^\d+$/.test(age)) errors.push({ path: "product.ageYears", code: "INT", message: "정수를 입력하세요." });
  if (abv && !Number.isFinite(Number(abv))) errors.push({ path: "product.abv", code: "FLOAT_PARSING" });
  if (errors.length) {
    const rest = showCheckFieldErrors(form, errors);
    if (rest.length) setCheckNotice("error", rest.join(" "));
    return null;
  }
  clearCheckFieldErrors(form);
  return {
    resolution: "create_and_link",
    brand: isNew
      ? { type: "new", canonicalName: value("brand.canonicalName"), aliases: [] }
      : { type: "existing", brandId: value("brand.brandId") },
    product: {
      category: "whisky",
      displayName: value("product.displayName"),
      ageYears: age ? Number(age) : null,
      editionName: value("product.editionName") || null,
      abv: abv ? Number(abv) : null,
    },
    aliases: readAliases(form, "aliases"),
  };
}

async function searchBrands(query, results, onPick) {
  if (!query.trim()) {
    results.replaceChildren(el("p", { class: "hint" }, "브랜드 이름이나 별칭을 입력하세요."));
    return;
  }
  results.replaceChildren(el("p", { class: "hint" }, "찾는 중..."));
  try {
    const found = await api("GET", `/api/catalog/brands?${new URLSearchParams({ query: query.trim(), limit: "20" })}`);
    results.replaceChildren(
      ...(found.items.length
        ? found.items.map((brand) =>
            el(
              "button",
              { type: "button", class: "candidate", onclick: () => onPick(brand) },
              brand.canonicalName,
              brand.matchedAlias !== brand.canonicalName ? el("span", { class: "hint" }, ` 별칭: ${brand.matchedAlias}`) : null,
            ),
          )
        : [el("p", { class: "hint" }, "맞는 브랜드가 없습니다. 새 브랜드로 등록하세요.")]),
    );
  } catch (error) {
    if (error.status !== 401) results.replaceChildren(el("p", { class: "error-text" }, error.message));
  }
}

function setCheckBusy(busy) {
  checks.busy = busy;
  const actions = $("check-actions");
  if (actions) actions.disabled = busy;
  $("check-rows").classList.toggle("busy", busy);
  // While a resolve runs the list cannot be reloaded, so no list response can predate it.
  for (const control of $("check-filters").elements) control.disabled = busy;
  $("checks-load-more").disabled = busy;
  $("checks-retry").disabled = busy;
}

// `productLabel` names the product a link resolves to, shown when the line moved (movedLink).
async function resolveCheck(check, body, form, productLabel = null) {
  if (checks.busy) return;
  setCheckBusy(true);
  setCheckNotice("warn", "처리하는 중...");
  const session = checks.session;
  let linked = false;
  try {
    const resolved = await api("POST", `/api/menu-item-checks/${encodeURIComponent(check.checkId)}/resolve`, body);
    if (session !== checks.session) return; // signed out meanwhile: show nothing of the old session
    if (productLabel) checks.resolvedProducts.set(resolved.checkId, productLabel);
    replaceCheck(resolved);
    renderCheckDetail(resolved);
    setCheckNotice("ok", RESOLVED_TEXT[body.resolution]);
    linked = body.resolution === "link_existing" || body.resolution === "create_and_link";
  } catch (error) {
    if (error.status === 401 || session !== checks.session) return;
    handleResolveError(check, error, form);
  } finally {
    if (session === checks.session) setCheckBusy(false);
  }
  // A link may move or merge the line, which can open or extend a price_conflict check on another
  // item (3.14.1); the answer has only this check, so the list is loaded again.
  if (linked) loadChecks(true, { keepDetail: true, keepPages: true });
}

function handleResolveError(check, error, form) {
  switch (error.code) {
    case "MENU_ITEM_CHECK_NOT_FOUND":
      closeCheckDetail("확인을 찾을 수 없습니다. 목록을 다시 불러옵니다.");
      loadChecks(true);
      return;
    case "INVALID_CHECK_STATE":
      closeCheckDetail("이미 처리되었거나 닫힌 확인입니다. 목록을 다시 불러옵니다.");
      loadChecks(true);
      return;
    case "BAR_NOT_FOUND":
      setCheckNotice("error", "업장이 비활성 상태라 처리하지 않았습니다. 업장을 다시 활성화한 뒤 처리하세요.");
      return;
    case "ACTIVE_IMPORT_EXISTS":
      setCheckNotice(
        "warn",
        "이 업장에 끝나지 않은 메뉴 등록 작업이 있어 아무것도 바꾸지 않았습니다. 업주의 검수가 끝난 뒤 다시 처리하세요. 다른 확인을 먼저 처리해도 됩니다.",
      );
      return;
    case "DUPLICATE_PRODUCT_FOUND": {
      const existing = error.details && error.details.existingProduct;
      if (existing && !existing.isActive) {
        // An inactive product cannot be linked (PRODUCT_INACTIVE), so no link button is offered.
        setCheckNotice(
          "error",
          el("p", {}, `같은 상품이 비활성 상태로 등록되어 있습니다: ${existing.displayName}`),
          el("p", {}, "상품을 다시 활성화한 뒤 연결하거나, 위에서 다른 활성 상품을 검색해 연결하세요."),
        );
        return;
      }
      setCheckNotice(
        "error",
        el("p", {}, error.message),
        existing
          ? el(
              "button",
              {
                type: "button",
                onclick: () => {
                  const aliasesToAdd = form ? readAliases(form, "aliases") : [];
                  if (window.confirm(`'${check.item.displayName}'을 기존 상품 '${existing.displayName}'에 연결할까요?`)) {
                    resolveCheck(
                      check,
                      { resolution: "link_existing", productId: existing.productId, aliasesToAdd },
                      form,
                      productText(existing),
                    );
                  }
                },
              },
              `기존 상품 '${existing.displayName}'에 연결`,
            )
          : null,
      );
      return;
    }
    case "DUPLICATE_BRAND_FOUND": {
      const existing = error.details && error.details.existingBrand;
      setCheckNotice(
        "error",
        el("p", {}, error.message),
        existing && form && form.pickBrand
          ? el(
              "button",
              {
                type: "button",
                onclick: () => {
                  form.pickBrand(existing.brandId, existing.canonicalName);
                  setCheckNotice("warn", `기존 브랜드 '${existing.canonicalName}'로 바꿨습니다. 다시 '등록하고 연결'을 누르세요.`);
                },
              },
              `기존 브랜드 '${existing.canonicalName}'로 바꾸기`,
            )
          : null,
      );
      return;
    }
    case "VALIDATION_FAILED": {
      const rest = form ? showCheckFieldErrors(form, error.fieldErrors) : error.fieldErrors.map((e) => e.message);
      setCheckNotice("error", rest.length ? rest.join(" ") : "입력한 값을 확인하세요.");
      return;
    }
    case "TEMPORARY_WRITE_CONFLICT":
      setCheckNotice("warn", "다른 요청과 겹쳐 저장하지 못했습니다. 잠시 후 같은 처리를 다시 시도하세요.");
      return;
    case "FORBIDDEN":
      showMessage("operator 권한이 없는 계정입니다.");
      return;
    default:
      setCheckNotice("error", error.message);
  }
}

// ---------- wiring ----------

$("tab-applications").addEventListener("click", () => selectTab("applications"));
$("tab-checks").addEventListener("click", () => selectTab("checks"));
$("check-filters").addEventListener("change", (event) => {
  if (event.target.name !== "status") return;
  checks.filters.status = event.target.value;
  loadChecks(true);
});
$("check-filters").addEventListener("submit", (event) => {
  event.preventDefault();
  findBars(event.target.elements.barQuery.value);
});
$("checks-refresh").addEventListener("click", () => loadChecks(true));
$("checks-load-more").addEventListener("click", () => loadChecks(false));
