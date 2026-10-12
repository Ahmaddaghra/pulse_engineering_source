"use strict";
/* View functions are pure HTML builders; mutations are centralized in dispatch/action. */
const $ = (id) => document.getElementById(id);
const clone = (value) => JSON.parse(JSON.stringify(value));
let state;
let toastTimer;
let returnFocus;
const L = (ar, en) => (state.lang === "ar" ? ar : en);
const tx = (pair) => pair[state.lang === "ar" ? 0 : 1];
const esc = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const navItems = [
  ["overview", "home", "نظرة عامة", "Overview"],
  ["emerging", "bolt", "الأحداث الناشئة", "Emerging Events"],
  ["event", "file", "تحليل الحدث", "Event Intelligence"],
  ["forecast", "chart", "الذكاء التنبؤي", "Predictive Intelligence"],
  ["workspace", "pen", "مساحة التحرير", "Editorial Workspace"],
  ["health", "shield", "سلامة المصادر", "Source Health"],
  ["how", "help", "كيف يعمل PULSE", "How PULSE Works"],
];
const beats = {
  all: ["الكل", "All"],
  transport: ["النقل والمواصلات", "Transport"],
  technology: ["التقنية", "Technology"],
  sport: ["الرياضة", "Sports"],
  culture: ["الثقافة والفنون", "Culture"],
  economy: ["الاقتصاد", "Economy"],
};
const statuses = {
  new: ["للمراجعة", "Review"],
  assigned: ["مُكلّف", "Assigned"],
  verify: ["طلب تحقق", "Verification"],
  watch: ["قيد المتابعة", "Watching"],
  snoozed: ["مؤجل", "Snoozed"],
  dismissed: ["مستبعد", "Dismissed"],
  covered: ["سبق تغطيته", "Already covered"],
};
const healthNames = {
  ok: ["سليم", "Healthy"],
  stale: ["تغذية متأخرة", "Delayed feed"],
  limited: ["حد الطلبات", "Rate limited"],
  unavailable: ["بيانات غير متاحة", "Data unavailable"],
};
const editors = {
  sara: ["سارة — الاقتصاد", "Sara — Economy"],
  omar: ["عمر — الشؤون المحلية", "Omar — Local desk"],
  noura: ["نورة — التقنية", "Noura — Technology"],
};
const actionNames = {
  assign: ["إسناد", "Assign"],
  verify: ["طلب تحقق", "Request verification"],
  watch: ["متابعة", "Watch"],
  snooze: ["تأجيل", "Snooze"],
  dismiss: ["استبعاد", "Dismiss"],
  covered: ["سبق تغطيته", "Mark already covered"],
  restore: ["إعادة للمراجعة", "Restore to review"],
};
const paths = {
  home: "M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9",
  bolt: "m13 2-9 12h7l-1 8 10-12h-7l0-8",
  file: "M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7",
  chart: "M4 20V13h4v7M10 20V8h4v12M16 20V3h4v17",
  pen: "m4 16 12-12 4 4L8 20H4zM14 6l4 4",
  shield: "m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 12l3 3 5-6",
  help: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M9 9c0-4 7-4 6 0-.5 2-3 2-3 5M12 17h.01",
  search: "M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16m6-2 6 6",
  users:
    "M16 21v-2c0-3-3-5-6-5s-6 2-6 5v2M10 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8M17 3c5 0 5 7 0 7M18 14c3 1 4 3 4 6",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18M12 7v6l4 2",
  arrow: "M5 12h14m-5-5 5 5-5 5",
  pulse: "M1 20h7l5-12 6 29 7-34 5 24 5-7h7",
};
const icon = (name) =>
  `<svg class="icon" viewBox="${name === "pulse" ? "0 0 44 40" : "0 0 24 24"}" aria-hidden="true"><path d="${paths[name] || paths.file}"/></svg>`;
const btn = (label, cmd, extra = "", cls = "") =>
  `<button ${cls ? `class="${cls}"` : ""} data-cmd="${cmd}" ${extra}>${label}</button>`;
const tag = (label, cls = "") => `<span class="tag ${cls}">${label}</span>`;
const eventById = (id) => PULSE_DATA.events.find((e) => e.id === id);
const workflow = (e) => state.workflows[e.id];
const sourceById = (id) => state.sources.find((s) => s.id === id);
const lastHourCount = (id) =>
  PULSE_DATA.events.reduce(
    (sum, e) =>
      sum +
      e.evidence.filter((r) => r[0] === id && Number(r[1].split(":")[0]) === 14)
        .length,
    0,
  );
const publishers = (e) => [...new Set(e.evidence.map((row) => row[0]))];
const origins = (e) => [
  ...new Set(e.evidence.map((row) => row[3]).filter(Boolean)),
];
const owners = (e) => [
  ...new Set(publishers(e).map((id) => sourceById(id).owner)),
];
const affected = (e) =>
  publishers(e).filter(
    (id) =>
      sourceById(id).health !== "ok" ||
      !sourceById(id).complete ||
      sourceById(id).gap,
  );
const healthyCount = () =>
  state.sources.filter((s) => s.health === "ok").length;
const active = (e) =>
  !["dismissed", "covered", "snoozed"].includes(workflow(e).status);
const verLabel = (e) =>
  e.verification === "partial"
    ? L("تحقق جزئي", "Partially verified")
    : L("غير متحقق", "Unverified");
const statusTag = (e) =>
  tag(
    tx(statuses[workflow(e).status]),
    workflow(e).status === "assigned"
      ? "blue"
      : workflow(e).status === "verify"
        ? "amber"
        : "",
  );
function initialState(lang = "ar") {
  return {
    lang,
    view: "overview",
    selected: "transport",
    beat: "all",
    filter: "all",
    query: "",
    range: 6,
    horizon: 24,
    baseline: false,
    demo: null,
    sources: clone(PULSE_DATA.sources),
    workflows: Object.fromEntries(
      PULSE_DATA.events.map((e) => [
        e.id,
        { status: e.initial, editor: e.editor || null, deadline: null },
      ]),
    ),
    activity: [],
  };
}
state = initialState();
function toast(message) {
  $("toast").textContent = message;
  $("toast").classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.remove("show"), 3000);
}
function navigate(view) {
  state.view = view;
  render();
  $("main").focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "instant" });
}
function addActivity(kind, eventId, detail = null) {
  state.activity.unshift({ kind, eventId, detail, at: new Date() });
}
function currentTitle() {
  const n = navItems.find((n) => n[0] === state.view);
  return L(n[2], n[3]);
}
function sidebar() {
  return `<div class="brand">${icon("pulse")}<span>PULSE</span></div><div class="brand-sub">EDITORIAL INTELLIGENCE</div><nav class="nav" aria-label="${L("التنقل الرئيسي", "Main navigation")}">${navItems.map((n) => `<button data-cmd="nav" data-view="${n[0]}" class="${state.view === n[0] ? "active" : ""}" ${state.view === n[0] ? 'aria-current="page"' : ""}>${icon(n[1])}<span>${L(n[2], n[3])}</span></button>`).join("")}</nav><div class="sidebar-bottom"><div class="person"><span class="avatar">${L("م ت", "DE")}</span><div><strong class="small">${L("محرر العرض", "Demo editor")}</strong><p class="muted small">${L("مساحة عمل توضيحية", "Illustrative workspace")}</p></div></div>${btn(L("إعادة ضبط العرض", "Reset Demo"), "reset")}</div>`;
}
function topbar() {
  return `<label class="search">${icon("search")}<input id="search" type="search" aria-label="${L("ابحث في الأحداث", "Search events")}" placeholder="${L("ابحث في الأحداث أو الزوايا التحريرية…", "Search events or editorial angles…")}" value="${esc(state.query)}"></label><div class="top-meta"><span class="date">${L("12 أكتوبر 2026 · 15:00 الرياض", "12 Oct 2026 · 15:00 Riyadh")}</span>${btn(L("English", "العربية"), "language", 'lang="' + (state.lang === "ar" ? "en" : "ar") + '"')} ${tag(L("نسخة تجريبية — بيانات خيالية", "Prototype — Illustrative Data"))}</div>`;
}
function pageHead(title, sub, extra = "") {
  return `<div class="page-head"><div><h1>${title}</h1><p>${sub}</p></div><div class="head-actions">${extra}${btn(L("تشغيل العرض الموجّه", "Guided Demo"), "demo-start", "", "primary")}</div></div>`;
}
function panel(title, body, extra = "", cls = "") {
  return `<section class="panel ${cls}"><div class="panel-head"><h2>${title}</h2>${extra}</div>${body}</section>`;
}
function notice(text, cls = "") {
  return `<div class="notice ${cls}">${text}</div>`;
}
function qualityBanner(e = null) {
  const ids = e
    ? affected(e)
    : state.sources
        .filter((s) => s.health !== "ok" || !s.complete || s.gap)
        .map((s) => s.id);
  return ids.length
    ? `<div class="quality-banner">${notice(L("تغطية جزئية: توجد فجوات أو قيود في ", "Partial coverage: gaps or restrictions in ") + ids.map((id) => "Publisher " + id).join(" · ") + L(". الملاحظات السابقة محفوظة؛ غياب الرصد لا يعني غياب الخبر.", ". Historical observations retained; no observation does not mean no news."))}</div>`
    : "";
}
function stats() {
  const a = PULSE_DATA.events.filter(active).length;
  return `<div class="stats">${[
    [a, L("تطورات في المراجعة", "Active developments"), "file"],
    [
      state.sources.length,
      L("جهات نشر خيالية", "Fictional publishers"),
      "users",
    ],
    [
      healthyCount() + "/" + state.sources.length,
      L("مصادر سليمة الآن", "Currently healthy sources"),
      "shield",
    ],
    [
      PULSE_DATA.events.filter((e) => workflow(e).status === "assigned").length,
      L("أحداث مُكلّفة", "Assigned events"),
      "pen",
    ],
  ]
    .map(
      ([v, t, i]) =>
        `<div class="stat">${icon(i)}<div><strong class="mono">${v}</strong><span>${t}</span></div></div>`,
    )
    .join("")}</div>`;
}
function beatFilters() {
  return `<div class="filters" role="group" aria-label="${L("التخصص", "Beat filter")}">${Object.entries(
    beats,
  )
    .map(([k, v]) =>
      btn(
        tx(v),
        "beat",
        `data-beat="${k}" aria-pressed="${state.beat === k}"`,
        state.beat === k ? "active" : "",
      ),
    )
    .join("")}</div>`;
}
function filteredEvents(includeInactive = false) {
  const q = state.query.toLocaleLowerCase().trim();
  return PULSE_DATA.events.filter(
    (e) =>
      (includeInactive || active(e)) &&
      (state.beat === "all" || e.beat === state.beat) &&
      (state.filter === "all" || workflow(e).status === state.filter) &&
      (!q ||
        [
          ...e.title,
          ...e.latest,
          ...e.relevance,
          ...e.opportunity,
          ...beats[e.beat],
          ...publishers(e).map((id) => "Publisher " + id),
        ]
          .join(" ")
          .toLocaleLowerCase()
          .includes(q)),
  );
}
function momentum(e) {
  const early = e.series6.slice(0, 3).reduce((a, b) => a + b, 0),
    recent = e.series6.slice(3).reduce((a, b) => a + b, 0);
  return `${early} → ${recent}`;
}
function eventRow(e) {
  const unknown = e.evidence.some((r) => r[3] === null);
  return `<article class="event-row ${e.id === "transport" ? "featured" : ""} ${state.demo === 0 && e.id === "transport" ? "demo-highlight" : ""}"><div><div class="metadata">${tag(tx(beats[e.beat]), e.beat === "technology" ? "blue" : e.beat === "transport" ? "amber" : "")}<span class="muted small">${L("أول رصد", "First observed")} <bdi class="mono">${e.first}</bdi></span>${tag(L("سيناريو خيالي", "Fictional scenario"))}</div><h3 class="event-title">${tx(e.title)}</h3><p class="excerpt">${L("أحدث تغير: ", "Latest change: ")}${tx(e.latest)}</p><div class="row-foot">${statusTag(e)}${tag(verLabel(e), "amber")}<span class="muted">${L("أدلة وصفية", "Metadata evidence")} · ${e.evidence.length} ${L("ملاحظات", "observations")}</span></div><p class="excerpt" style="margin-top:7px">${tx(e.relevance)}</p>${
    affected(e).length
      ? `<p class="gap-line">${L("فجوة رصد: ", "Observation gap: ")}${affected(
          e,
        )
          .map((id) => "Publisher " + id)
          .join(", ")}</p>`
      : ""
  }</div><div class="event-numbers"><div><span>${L("جهات نشر", "Publishers")}</span><strong class="mono">${publishers(e).length}</strong><span>${owners(e).length} ${L("مجموعات ملكية", "owner groups")}</span></div><div><span>${L("أصول تقارير", "Reporting origins")}</span><strong class="mono">${origins(e).length}${unknown ? "+ ?" : ""}</strong><span>${L("لا تعني تأكيدًا", "Not corroboration")}</span></div></div><div class="row-action"><div><div class="spark" aria-hidden="true">${e.series6.map((v) => `<i style="height:${5 + v * 5}px"></i>`).join("")}</div><p class="bars-label">${momentum(e)} ${L("مقالات / 3س", "articles / 3h")}</p></div>${btn(L("عرض التفاصيل", "Open details"), "open", `data-event="${e.id}"`)}</div></article>`;
}
function healthSummary() {
  const radius = 35,
    circ = 2 * Math.PI * radius;
  return panel(
    L("سلامة المصادر", "Source health"),
    `<div class="panel-body"><div class="health-ring"><div class="ring"><svg viewBox="0 0 90 90" aria-hidden="true"><circle cx="45" cy="45" r="35" stroke="#efbf68"/><circle cx="45" cy="45" r="35" stroke="#55dec1" stroke-dasharray="${(circ * healthyCount()) / 6} ${circ}"/></svg><strong class="mono">${healthyCount()}/6</strong></div><div><h3>${L("مصادر سليمة", "Healthy sources")}</h3><p class="muted small">${L("الاكتمال لا يُستنتج من الاتصال", "Connectivity ≠ completeness")}</p></div></div><div class="health-list">${Object.entries(
      healthNames,
    )
      .map(
        ([k, v]) =>
          `<div class="health-item"><span class="dot ${k === "ok" ? "" : k === "unavailable" ? "muted" : "amber"}"></span>${tx(v)}<b class="mono">${state.sources.filter((s) => s.health === k).length}</b></div>`,
      )
      .join(
        "",
      )}</div><div style="margin-top:18px">${notice(L("اكتمال اللوحة غير مؤكد. العلامات التابعة لمالك واحد ليست مصادر مستقلة.", "Panel completeness is uncertain. Brands with one owner are not independent sources."))}</div></div>`,
    btn(L("إدارة", "Manage"), "nav", 'data-view="health"', "", ""),
  );
}
function activityText(a) {
  if (a.kind === "health")
    return (
      L("تغيير حالة ", "Changed status of ") +
      "Publisher " +
      a.detail.source +
      " · " +
      tx(healthNames[a.detail.health])
    );
  if (a.kind === "resume")
    return L(
      "انتهى التأجيل؛ انتقل إلى المتابعة",
      "Snooze expired; moved to Watching",
    );
  return (
    tx(actionNames[a.kind]) +
    (a.detail
      ? " · " +
        (editors[a.detail]
          ? tx(editors[a.detail])
          : a.kind === "snooze"
            ? a.detail + L(" دقيقة", " minutes")
            : a.detail)
      : "")
  );
}
function activityList(limit = 8) {
  if (!state.activity.length)
    return `<div class="activity-item"><p>${L("إسناد أولي: سارة — الاقتصاد", "Initial assignment: Sara — Economy")}</p><small>${tx(eventById("economy").title)}</small></div><div class="activity-item"><p>${L("طلب تحقق أولي: معيار النماذج العربية", "Initial verification: Arabic benchmark")}</p><small>${L("حالة البداية الخيالية؛ جرّب إجراءً جديدًا", "Fictional starting state; try an action")}</small></div>`;
  return state.activity
    .slice(0, limit)
    .map(
      (a) =>
        `<div class="activity-item"><div style="display:flex;justify-content:space-between;gap:10px"><p>${esc(activityText(a))}</p><small class="mono">${a.at.toLocaleTimeString(state.lang === "ar" ? "ar-SA" : "en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Riyadh" })}</small></div>${a.eventId ? `<small>${tx(eventById(a.eventId).title)}</small>` : ""}</div>`,
    )
    .join("");
}
function overview(emerging = false) {
  const events = filteredEvents();
  return (
    pageHead(
      emerging
        ? L("الأحداث الناشئة", "Emerging events")
        : L("مركز القرار التحريري", "Editorial command center"),
      L(
        "تطورات تستحق قرارًا تحريريًا — لقطة خيالية ثابتة، وليست أخبارًا حية.",
        "Developments that deserve an editorial decision — a fixed fictional checkpoint.",
      ),
    ) +
    stats() +
    `<div class="workbench"><section><div class="panel"><div class="panel-head"><h2>${L("فرص تحريرية ناشئة", "Emerging editorial opportunities")}</h2>${tag(L("رصد توضيحي · OBSERVED", "Illustrative · OBSERVED"), "teal")}</div>${beatFilters()}</div>${emerging ? `<div class="toolbar" style="margin-top:15px"><label class="selection-label" for="status-filter">${L("الحالة", "Status")}</label><select id="status-filter">${["all", "new", "assigned", "verify", "watch"].map((s) => `<option value="${s}" ${state.filter === s ? "selected" : ""}>${s === "all" ? L("كل الحالات", "All statuses") : tx(statuses[s])}</option>`).join("")}</select><span class="small muted">${events.length} ${L("نتائج", "results")}</span></div>` : ""}<div class="list" style="margin-top:10px">${events.length ? events.map(eventRow).join("") : `<div class="panel empty">${L("لا توجد أحداث تطابق هذا العرض. هذا لا يثبت غياب الأخبار؛ حدود الرصد ما زالت قائمة.", "No events match this view. This does not establish no news; observation limits still apply.")}${btn(L("مسح المرشحات", "Clear filters"), "clear", 'style="display:block;margin:15px auto 0"')}</div>`}</div></section><aside class="side-rail">${healthSummary()}${panel(L("النشاط التحريري", "Editorial activity"), `<div class="panel-body">${activityList(4)}</div>`, btn(L("المساحة", "Workspace"), "nav", 'data-view="workspace"'))}${panel(L("ما الذي تغير؟", "What changed?"), `<div class="panel-body"><p class="small muted">${L("خمسة تطورات مادية؛ جميع الادعاءات بحاجة إلى استكمال التحقق. زخم الرصد هو عدد المقالات في آخر 3 ساعات مقابل الساعات الثلاث السابقة.", "Five material developments; all claims need further verification. Momentum compares article counts in the last three hours with the preceding three.")}</p></div>`)}</aside></div>`
  );
}
function selector() {
  return `<label class="selection-label" for="event-select">${L("الحدث", "Event")}</label><select id="event-select">${PULSE_DATA.events.map((e) => `<option value="${e.id}" ${e.id === state.selected ? "selected" : ""}>${tx(e.title)}</option>`).join("")}</select>`;
}
function observedSeries(e) {
  if (state.range === 6)
    return {
      values: e.series6,
      labels: ["09–10", "10–11", "11–12", "12–13", "13–14", "14–15"],
      unit: L("مقالات في الساعة", "Articles per hour"),
    };
  if (state.range === 24)
    return {
      values: [...e.past24, e.series6.reduce((a, b) => a + b, 0)],
      labels: [
        "11 Oct 15–18",
        "18–21",
        "21–00",
        "00–03",
        "03–06",
        "06–09",
        "09–15",
      ],
      unit: L("مقالات في الفترات المبينة", "Articles in labeled intervals"),
    };
  return {
    values: [
      ...e.days,
      e.past24.reduce((a, b) => a + b, 0) +
        e.series6.reduce((a, b) => a + b, 0),
    ],
    labels: [
      "05–06 Oct",
      "06–07 Oct",
      "07–08 Oct",
      "08–09 Oct",
      "09–10 Oct",
      "10–11 Oct",
      "11–12 Oct",
    ],
    unit: L(
      "مقالات في فترات 24 ساعة تنتهي عند 15:00 الرياض",
      "Articles in 24-hour intervals ending at 15:00 Riyadh",
    ),
  };
}
function timeline(e) {
  const d = observedSeries(e),
    max = Math.max(...d.values, 4),
    n = d.values.length,
    w = 640,
    h = 220,
    left = 42,
    bottom = 180,
    step = 560 / n;
  return `<div class="chart-wrap"><svg class="chart" viewBox="0 0 ${w} ${h}" role="group" aria-label="${L("نشاط النشر الخيالي", "Fictional publication activity")}">${[
    0, 1, 2, 3,
  ]
    .map((i) => {
      const v = Math.ceil((max * i) / 3),
        y = bottom - (v / max) * 140;
      return `<line class="grid-line" x1="40" x2="620" y1="${y}" y2="${y}"/><text x="28" y="${y + 4}" text-anchor="end">${v}</text>`;
    })
    .join(
      "",
    )}${d.values.map((v, i) => `<rect class="bar" x="${left + i * step + 12}" y="${bottom - (v / max) * 140}" width="${step - 24}" height="${Math.max((v / max) * 140, 2)}" rx="3" tabindex="0" role="button" data-chart-index="${i}" data-chart-label="${d.labels[i]}" data-chart-value="${v}" aria-label="${d.labels[i]}: ${v} ${L("مقالات خيالية", "fictional articles")}"><title>${d.labels[i]}: ${v}</title></rect><text x="${left + i * step + step / 2}" y="205" text-anchor="middle" font-size="${state.range === 24 ? 9 : 11}">${d.labels[i]}</text>`).join("")}</svg></div><div id="chart-inspect" class="chart-inspect" role="status">${L("اختر عمودًا لقراءة العدد في الفترة.", "Select a bar to inspect its period count.")}</div><div class="chart-caption">${d.values.reduce((a, b) => a + b, 0)} ${L("ملاحظات نشر خيالية", "fictional publication observations")} · ${d.unit}. ${L("التكرار عبر الناشرين لا يزيد عدد أصول التقارير.", "Syndication across publishers does not add reporting origins.")}</div>`;
}
function evidenceTable(e) {
  const klass = {
    original: ["أصل تقريري", "Original report"],
    syndicated: ["إعادة نشر", "Syndicated"],
    unknown: ["أصل غير محسوم", "Origin unknown"],
  };
  return `<p class="scroll-hint">${L("مرّر الجدول أفقياً للاطلاع على الأدلة والقيود وأدوات المحاكاة.", "Scroll the table horizontally for evidence, restrictions and simulation controls.")}</p><div class="table-wrap" tabindex="0" role="region" aria-label="${L("جدول قابل للتمرير", "Scrollable data table")}"><table><thead><tr><th>${L("جهة النشر / الرصد", "Publisher / observed")}</th><th>${L("عنوان المقال الخيالي", "Fictional article title")}</th><th>${L("النسب", "Lineage")}</th><th>${L("الدليل وحدوده", "Evidence and limits")}</th></tr></thead><tbody>${e.evidence.map((r) => `<tr><td><span class="source-title">Publisher ${r[0]}</span><p class="mono">12 Oct · ${r[1]} AST</p>${sourceById(r[0]).health !== "ok" || sourceById(r[0]).gap ? tag(L("فجوة في الرصد", "Observation gap"), "amber") : ""}</td><td>${tx(r[4])}</td><td>${tag(tx(klass[r[2]]), r[2] === "original" ? "teal" : "")}<p>${r[3] ? L("أصل ", "Origin ") + r[3] : L("غير معروف", "Unknown")}</p></td><td>${tx(r[5])}</td></tr>`).join("")}</tbody></table></div>`;
}
function actionButtons(e) {
  return `<div class="action-grid">${Object.entries(actionNames)
    .filter(([k]) => k !== "restore")
    .map(([k, v]) =>
      btn(
        tx(v),
        "action",
        `data-action="${k}" data-event="${e.id}"`,
        k === "assign" ? "primary" : "",
      ),
    )
    .join("")}</div>`;
}
function eventView() {
  const e = eventById(state.selected);
  return (
    pageHead(
      tx(e.title),
      L(
        "تحليل الحدث · سيناريو خيالي · أول رصد ",
        "Event intelligence · Fictional scenario · First observed ",
      ) + e.first,
    ) +
    `<div class="toolbar">${selector()}${statusTag(e)}${tag(verLabel(e), "amber")}</div>` +
    qualityBanner(e) +
    `<div class="split"><div class="stack">${panel(
      L("ملخص التطور", "Development overview"),
      `<div class="panel-body overview-copy">${[
        [L("ماذا حدث؟", "What happened?"), e.what],
        [L("ما الذي تغير؟", "What changed?"), e.latest],
        [L("لماذا يهم؟", "Why relevant?"), e.relevance],
        [L("ما الذي لم يُتحقق منه؟", "What remains unverified?"), e.unknown],
      ]
        .map(([h, p]) => `<div><h3>${h}</h3><p>${tx(p)}</p></div>`)
        .join("")}</div>`,
    )}${panel(L("مسار التغطية المرصودة", "Observed coverage timeline"), timeline(e), `<div class="segments" role="group" aria-label="${L("فترة الرصد", "Observed range")}">${[6, 24, 168].map((r) => btn(r === 168 ? L("7 أيام", "7 days") : r + L(" ساعات", " hours"), "range", `data-range="${r}" aria-pressed="${state.range === r}"`, state.range === r ? "active" : "")).join("")}</div>`)}${panel(L("أدلة المصادر", "Source evidence"), evidenceTable(e), tag(L("مراجع خيالية؛ بلا روابط", "Fictional labels; no links")))}</div><aside class="stack">${panel(L("الفرصة التحريرية", "Editorial opportunity"), `<div class="panel-body"><h3 class="teal">${tx(e.recommendation)}</h3><p>${tx(e.opportunity)}</p>${notice(L("مخرج توضيحي لدعم القرار؛ ليس توصية مثبتة تجريبيًا. المحرر مسؤول عن القرار.", "Illustrative editorial support, not an empirically validated recommendation. The editor decides."), "neutral")}${actionButtons(e)}<p class="small">${L("الحالة الحالية: ", "Current state: ")}${tx(statuses[workflow(e).status])}${workflow(e).editor ? " · " + tx(editors[workflow(e).editor]) : ""}</p></div>`, tag("SIMULATED", "teal"), "opportunity " + (state.demo === 2 ? "demo-highlight" : ""))}${panel(L("تنوع الرصد", "Observation diversity"), `<div class="panel-body"><div class="event-numbers" style="border:0;padding:0"><div><strong>${publishers(e).length}</strong><span>${L("جهات نشر", "Publishers")}</span></div><div><strong>${origins(e).length}${e.evidence.some((r) => r[3] === null) ? " + ?" : ""}</strong><span>${L("أصول تقارير معروفة", "Known reporting origins")}</span></div></div><p class="small muted" style="margin-top:20px">${owners(e).length} ${L("مجموعات ملكية. اتساع التوزيع ليس تأكيدًا مستقلًا؛ حتى الأصل المستقل يحتاج تحققًا.", "owner groups. Distribution breadth is not independent corroboration; even an independent origin needs verification.")}</p></div>`)}</aside></div>`
  );
}
function workspace() {
  return (
    pageHead(
      L("مساحة التحرير", "Editorial workspace"),
      L(
        "حوّل الرصد إلى قرار. جميع الإجراءات محاكاة محلية في هذه الجلسة.",
        "Turn observations into decisions. All actions are local session simulations.",
      ),
      btn(L("إعادة ضبط العرض", "Reset Demo"), "reset"),
    ) +
    `<div class="toolbar">${tag("SIMULATED", "teal")}${tag(state.activity.length + " " + L("إجراءات في الجلسة", "session actions"))}</div><div class="board">${Object.entries(
      statuses,
    )
      .map(([s, label]) => {
        const items = PULSE_DATA.events.filter(
          (e) =>
            workflow(e).status === s &&
            (!state.query ||
              [...e.title, ...e.latest]
                .join(" ")
                .toLocaleLowerCase()
                .includes(state.query.toLocaleLowerCase())),
        );
        return `<section class="lane"><div class="lane-head"><h2>${tx(label)}</h2>${tag(items.length)}</div>${items.length ? items.map((e) => `<article class="board-card"><h3>${tx(e.title)}</h3><small>${tx(beats[e.beat])}${workflow(e).editor ? " · " + tx(editors[workflow(e).editor]) : ""}${workflow(e).deadline ? " · " + L("حتى ", "Until ") + new Date(workflow(e).deadline).toLocaleTimeString(state.lang === "ar" ? "ar-SA" : "en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Riyadh" }) + " AST" : ""}</small><div class="board-controls">${btn(L("الأدلة", "Evidence"), "open", `data-event="${e.id}"`)}${s === "new" || s === "verify" ? btn(L("إسناد", "Assign"), "action", `data-action="assign" data-event="${e.id}"`) : ""}${s === "new" || s === "assigned" || s === "verify" ? btn(L("متابعة", "Watch"), "action", `data-action="watch" data-event="${e.id}"`) : ""}${s === "new" ? btn(L("طلب تحقق", "Verify"), "action", `data-action="verify" data-event="${e.id}"`) : ""}${["snoozed", "dismissed", "covered", "watch"].includes(s) ? btn(L("إعادة للمراجعة", "Restore"), "action", `data-action="restore" data-event="${e.id}"`) : ""}</div></article>`).join("") : `<p class="muted small">${L("لا أحداث في هذا القسم", "No events in this section")}</p>`}</section>`;
      })
      .join(
        "",
      )}</div><div style="margin-top:20px">${panel(L("سجل نشاط الجلسة", "Session activity history"), `<div class="panel-body">${activityList(30)}</div>`)}</div>`
  );
}
function forecastChart(e) {
  const horizon = state.horizon,
    project = e.scenario[horizon],
    past = e.series6;
  const interval = horizon / project.length;
  const rate = past.slice(-3).reduce((a, b) => a + b, 0) / 3;
  const baseline = project.map(() => Math.round(rate * interval));
  const cumulative = (arr) => {
    let sum = 0;
    return arr.map((v) => (sum += v));
  };
  const history = cumulative([...e.past24, past.reduce((a, b) => a + b, 0)]),
    anchor = history.at(-1);
  const projected = cumulative(project).map((v) => anchor + v);
  const base = cumulative(baseline).map((v) => anchor + v);
  const spread = cumulative(project).map((v, i) =>
    Math.max(1, Math.round(v * (0.25 + i * 0.08))),
  );
  const max =
    Math.max(
      ...projected.map((v, i) => v + spread[i]),
      ...(state.baseline ? base : []),
    ) + 2;
  const y0 = 200,
    times = [
      -21,
      -18,
      -15,
      -12,
      -9,
      -6,
      0,
      ...project.map((_, i) => (i + 1) * interval),
    ];
  const point = (v, i) => [
    45 + ((times[i] + 24) / (24 + horizon)) * 600,
    y0 - (v / max) * 150,
  ];
  const path = (arr, start) =>
    arr.map((v, i) => point(v, start + i).join(",")).join(" ");
  const boundary = 45 + (24 / (24 + horizon)) * 600;
  const upper = projected.map((v, i) => point(v + spread[i], 7 + i));
  const lower = projected
    .map((v, i) => point(Math.max(anchor, v - spread[i]), 7 + i))
    .reverse();
  return `<div class="chart-wrap"><svg class="chart" viewBox="0 0 680 260" role="img" aria-label="${L("مقالات خيالية تراكمية منذ 24 ساعة قبل اللقطة، مع إسقاط افتراضي ونطاق غير إحصائي", "Cumulative fictional articles since 24 hours before cutoff, with hypothetical projection and non-statistical scenario band")}">${[
    0, 1, 2, 3,
  ]
    .map((i) => {
      const v = Math.round((max * i) / 3),
        y = y0 - (v / max) * 150;
      return `<line class="grid-line" x1="40" x2="655" y1="${y}" y2="${y}"/><text x="28" y="${y + 4}" text-anchor="end">${v}</text>`;
    })
    .join(
      "",
    )}<line x1="${boundary}" x2="${boundary}" y1="25" y2="205" stroke="#78909e" stroke-dasharray="4 5"/><text x="${boundary}" y="17" text-anchor="middle">${L("اللقطة الخيالية", "Fictional cutoff")}</text><polygon points="${[...upper, ...lower].map((p) => p.join(",")).join(" ")}" fill="#9bbcff" opacity=".13"/><polyline class="observed-line" points="${path(history, 0)}"/><polyline class="forecast-line" points="${point(anchor, 6).join(",")} ${path(projected, 7)}"/>${state.baseline ? `<polyline class="baseline-line" points="${point(anchor, 6).join(",")} ${path(base, 7)}"/>` : ""}<text x="45" y="228">−24h</text><text x="${boundary}" y="228" text-anchor="middle">12 Oct · 15:00 AST</text><text x="640" y="228" text-anchor="end">+${horizon === 168 ? "7d" : horizon + "h"}</text><text x="45" y="251">${L("مجموع تراكمي؛ مقياس واحد للعدد", "Cumulative articles; common count scale")}</text></svg></div><div class="legend"><span><i></i>${L("ملاحظات خيالية", "Fictional observed")}</span><span><i class="projected"></i>${L("إسقاط افتراضي", "Hypothetical projection")}</span>${state.baseline ? `<span><i class="baseline"></i>${L("استمرار الزخم", "Momentum continuation")}</span>` : ""}</div><div class="chart-caption">${L("النطاق المظلل مجرد نطاق سيناريو؛ ليس فترة ثقة ولا احتمالًا معايرًا. العدد تراكمي منذ بداية الساعات الـ24 المرصودة. محور الزمن متناسب مع مدة كل فترة.", "Shading is a scenario range, not a confidence interval or calibrated probability. Counts accumulate from the start of the observed 24 hours. The time axis is proportional to interval duration.")}</div><div class="panel-body" style="border-top:1px solid var(--line)"><div class="event-numbers" style="border:0;padding:0"><div><span>${L("الساعات الـ24 الماضية", "Past 24 hours")}</span><strong class="mono">${anchor}</strong><span>${L("ملاحظات خيالية", "Fictional observations")}</span></div><div><span>${L("الإسقاط الافتراضي القادم", "Hypothetical future total")}</span><strong class="mono">${project.reduce((a, b) => a + b, 0)}</strong><span>${horizon === 168 ? L("في 7 أيام", "Across 7 days") : horizon + L(" ساعات", " hours")}</span></div></div>${state.baseline ? `<p class="small muted" style="margin-top:15px">${L("خط الأساس: متوسط آخر 3 ساعات × طول الفترة. إجمالي افتراضي: ", "Baseline: mean of the last 3 hours × interval duration. Hypothetical total: ")}${baseline.reduce((a, b) => a + b, 0)}. ${L("لا توجد مقارنة أداء؛ هذه ليست نتائج نموذج.", "No performance comparison; these are not model results.")}</p>` : ""}</div>`;
}
function forecast() {
  const e = eventById(state.selected),
    gaps = affected(e);
  const eligible = !gaps.length;
  const past =
      e.past24.reduce((a, b) => a + b, 0) +
      e.series6.reduce((a, b) => a + b, 0),
    future = e.scenario[state.horizon].reduce((a, b) => a + b, 0);
  return (
    pageHead(
      L("الذكاء التنبؤي", "Predictive intelligence"),
      L(
        "إشارة بحثية محتملة لتخطيط التغطية؛ ليست تنبؤًا بوقوع خبر جديد.",
        "A possible research signal for coverage planning; not a prediction of a new incident.",
      ),
    ) +
    notice(
      L(
        "معاينة بحثية — إسقاطات توضيحية. لا يوجد نموذج تنبؤي مُتحقق منه متصل.",
        "Research Preview — Illustrative Forecasts. No validated predictive model is connected.",
      ),
      "research",
    ) +
    `<div class="toolbar" style="margin-top:20px">${selector()}<div class="segments" role="group" aria-label="${L("الأفق الافتراضي", "Hypothetical horizon")}">${[6, 24, 168].map((h) => btn(h === 168 ? L("7 أيام", "7 days") : h + L(" ساعات", " hours"), "horizon", `data-horizon="${h}" aria-pressed="${state.horizon === h}"`, state.horizon === h ? "active" : "")).join("")}</div></div>${notice(state.horizon === 24 ? L("24 ساعة: هدف البحث الأولي هو نمو عدد مرات النشر المرصودة ضمن لوحة مؤهلة لحدث معروف بالفعل.", "24 hours: the initial research target is growth in observed publication occurrences within a qualified panel for an already known event.") : L("هذا الأفق مفهوم تصميمي مستقبلي؛ ليس هدف البحث الأولي.", "This horizon is a future design concept, not the initial research target."), "neutral")}<div class="split" style="margin-top:20px"><div class="stack">${panel(L("مسار التغطية: مرصود ← افتراضي", "Coverage trajectory: observed → hypothetical"), eligible ? forecastChart(e) : `<div class="panel-body">${notice(L("الإسقاط غير متاح: فجوات في المصادر الداعمة ", "Projection unavailable: supporting source gaps in ") + gaps.map((id) => "Publisher " + id).join(" · "))}<p class="muted small" style="margin-top:18px">${L("تبقى الأدلة المرصودة قابلة للفحص. النتيجة غير المتاحة ليست صفرًا. استعادة الاتصال لا تمحو فجوة تاريخية؛ إعادة ضبط العرض تبدأ سيناريو نظيفًا.", "Observed evidence remains inspectable. Unavailable is not zero. Restoring connectivity does not erase a historical gap; reset starts a clean scenario.")}</p>${btn(L("فحص الأدلة المرصودة", "Inspect observed evidence"), "nav", 'data-view="event" style="margin-top:16px"')}</div>`, tag("RESEARCH", "blue"))}${panel(L("مقارنة مفهومية بخط أساس", "Conceptual baseline comparison"), `<div class="panel-body"><label class="check"><input id="baseline" type="checkbox" ${state.baseline ? "checked" : ""}>${L("إظهار استمرار الزخم البسيط", "Show simple momentum continuation")}</label><p class="small muted" style="margin-top:10px">${L("نفس الحدث والأفق والبيانات الخيالية. المقارنة تشرح فكرة الاختبار، ولا تدّعي تفوقًا.", "Same event, horizon and fictional inputs. This explains an evaluation concept without claiming superiority.")}</p></div>`)}</div><aside class="stack">${panel(L("قراءة الإشارة", "Reading the signal"), `<div class="panel-body"><h3 class="${eligible ? "teal" : "amber"}">${eligible ? tx(e.potential) : L("غير متاح بسبب جودة البيانات", "Unavailable due to data quality")}</h3><p class="muted small" style="margin-top:10px">${eligible && state.horizon === 24 ? L("فرق افتراضي في العدد: ", "Hypothetical count difference: ") + (future - past) + L(" مقالة. هذا وحده لا يثبت تحقق تعريف طفرة التغطية؛ حدود النمو وتنوع الملاك تحتاج تثبيتًا واختبارًا.", " articles. This alone does not satisfy a validated surge label; growth and owner thresholds require freezing and evaluation.") : L("لا احتمالات رقمية، ولا ادعاء دقة.", "No numeric probabilities or accuracy claims.")}</p></div>`)}${panel(L("عوامل محتملة", "Possible contributing factors"), `<div class="panel-body"><ul class="reason-list"><li>${L("تغير فعلي في الحدث؛ لا تكرار العنوان", "Material event change, beyond repeated headlines")}</li><li>${L("عدد مرات النشر ونموها عبر الوقت", "Publication count and growth over time")}</li><li>${L("تنوع الملاك مع فصل إعادة النشر", "Owner distribution with syndication separated")}</li><li>${L("عمر الحدث، الوقت والتخصص", "Event age, calendar and beat")}</li><li>${L("اكتمال المصادر وأهلية اللقطة", "Source completeness and snapshot eligibility")}</li></ul></div>`)}${panel(L("أثر محتمل على التخطيط", "Possible planning use"), `<div class="panel-body"><p class="small muted">${L("قد يدفع دعم تنبؤي مُؤهّل لاحقًا إلى تجهيز محرر أو متابعة موعد تحديث، مع استمرار القرار البشري. المعاينة الحالية لا تقود الإسناد تلقائيًا.", "Qualified predictive support could later help reserve editor time or monitor an update. Human control remains; this preview never assigns automatically.")}</p></div>`)}</aside></div><div style="margin-top:20px">${notice(L("التنبؤ بالتغطية لا يقيس اهتمام الجمهور أو الرأي العام. الرأي يحتاج بحثًا تمثيليًا، والاهتمام يحتاج قياسًا منفصلًا.", "Forecasting coverage does not measure audience attention or public opinion. Opinion requires representative research; attention requires a separate measurement protocol."), "neutral")}</div>`
  );
}
function health() {
  return (
    pageHead(
      L("سلامة المصادر", "Source health"),
      L(
        "حالة الاتصال، اكتمال الرصد وحقوق المصدر مفاهيم منفصلة — جميع المصادر خيالية.",
        "Connectivity, observation completeness and source rights are separate — all sources are fictional.",
      ),
    ) +
    qualityBanner() +
    panel(
      L("لوحة المصادر الخيالية", "Fictional source panel"),
      `<p class="scroll-hint">${L("مرّر الجدول أفقياً للاطلاع على الأدلة والقيود وأدوات المحاكاة.", "Scroll the table horizontally for evidence, restrictions and simulation controls.")}</p><div class="table-wrap" tabindex="0" role="region" aria-label="${L("جدول قابل للتمرير", "Scrollable data table")}"><table class="large-table"><thead><tr>${["جهة النشر|Publisher", "المالك|Owner", "الحالة|Health", "آخر تحديث مرصود|Last observed update", "آخر ساعة|Last hour", "الاكتمال / القيود|Completeness / restrictions", "محاكاة الحالة|Simulate health"].map((t) => `<th>${L(...t.split("|"))}</th>`).join("")}</tr></thead><tbody>${state.sources
        .map(
          (s) =>
            `<tr><td><strong class="source-title">Publisher ${s.id}</strong><p>${L("اسم توضيحي فقط", "Illustrative label only")}</p></td><td class="mono">${s.owner}<p>${L("مجموعة خيالية", "Fictional group")}</p></td><td>${tag(tx(healthNames[s.health]), s.health === "ok" ? "teal" : "amber")}</td><td class="mono">12 Oct · ${s.last} AST${s.gap ? `<p class="amber">${L("فجوة تاريخية محفوظة", "Historical gap retained")}</p>` : ""}</td><td>${s.health !== "ok" ? L("غير متاح", "Unavailable") : `<strong class="mono">${lastHourCount(s.id)}</strong>`}<p>${s.health === "ok" ? L("مقالات مرصودة خيالية", "Fictional observed articles") : L("ليس صفرًا", "Not zero")}</p></td><td>${tag(s.complete && !s.gap ? L("مكتمل في المثال", "Complete in fixture") : L("اكتمال غير معروف", "Unknown completeness"), s.complete && !s.gap ? "" : "amber")}<p>${tx(s.restriction)}</p></td><td><select class="status-select" data-source="${s.id}" aria-label="${L("محاكاة حالة ", "Simulate health for ")}Publisher ${s.id}">${Object.entries(
              healthNames,
            )
              .map(
                ([k, v]) =>
                  `<option value="${k}" ${k === s.health ? "selected" : ""}>${tx(v)}</option>`,
              )
              .join("")}</select></td></tr>`,
        )
        .join("")}</tbody></table></div>`,
      tag("SIMULATED", "teal"),
    ) +
    `<div class="concepts">${panel(L("صفر مرصود", "Observed zero"), `<div class="panel-body"><p>${L("Publisher E: صفر مقالات في الساعة الأخيرة ضمن المثال المكتمل؛ له ملاحظات تاريخية. هذا لا يعني غياب أخبار خارج اللوحة.", "Publisher E: zero in the last complete fixture hour; historical observations still exist. This does not establish no news outside the panel.")}</p></div>`)}${panel(L("بيانات غير متاحة", "Data unavailable"), `<div class="panel-body"><p>${L("لا نملك نافذة رصد صالحة؛ لا يجوز تحويل القيمة المجهولة إلى صفر.", "No usable observation window; an unknown value cannot become zero.")}</p></div>`)}${panel(L("مصدر متدهور", "Degraded source"), `<div class="panel-body"><p>${L("تأخر أو حد طلبات مع فجوات معلنة. الأدلة السابقة محفوظة؛ الإسقاط غير المدعوم غير متاح.", "Delay or rate limit with disclosed gaps. Prior evidence remains; unsupported projections are unavailable.")}</p></div>`)}</div><div style="margin-top:20px">${notice(L("جرّب خفض حالة Publisher A، ثم افحص النظرة العامة والحدث والإسقاط. تغيير الحالة لا يحذف الملاحظات أو يختلق مقالات. الاستعادة لا تعالج الفجوة الماضية؛ استخدم إعادة ضبط العرض لبدء المثال الأصلي.", "Degrade Publisher A, then inspect overview, event and projection. Health changes never delete observations or invent articles. Restoration retains the past gap; Reset Demo starts the original fixture."), "neutral")}</div>`
  );
}
function how() {
  const ops = [
    [
      "مصادر أخبار معتمدة",
      "Approved news sources",
      "سياسات وصول وحقوق وملكية معلنة؛ لا مصادر حقيقية متصلة هنا.",
      "Declared access, rights and ownership policies; no real integrations here.",
    ],
    [
      "التقاط البيانات والنسب",
      "Data ingestion & provenance",
      "إيصالات متينة، تخزين مسموح، وسجل تغييرات لا يُعاد كتابته.",
      "Durable receipts, permitted storage and append-only history.",
    ],
    [
      "اكتشاف الأحداث العربية وتجميعها",
      "Arabic event detection & clustering",
      "مطابقة دلالية عربية مع فصل الحدث عن المقال وعن عائلة إعادة النشر.",
      "Arabic semantic matching; separate events, articles and syndication families.",
    ],
    [
      "متابعة الأحداث وتحليل الأدلة",
      "Event monitoring & evidence analysis",
      "تمييز التطور الجديد والتكرار والأصول المعروفة والفجوات.",
      "Separate material changes, repeats, known origins and gaps.",
    ],
    [
      "تحديد الفرص التحريرية",
      "Editorial opportunity identification",
      "شرح مرتبط بالأدلة وأسئلة تحقق؛ لا نشر آلي.",
      "Evidence-bound explanation and verification questions; no automatic publishing.",
    ],
    [
      "قرار المحرر البشري",
      "Human editorial decision",
      "تحقق، إسناد، متابعة أو استبعاد؛ القرار للمحرر.",
      "Verify, assign, watch or dismiss; the editor decides.",
    ],
  ];
  const research = [
    [
      "بيانات تاريخية مؤهلة",
      "Historical qualified data",
      "نوافذ مكتملة وهويات وأزمنة قابلة لإعادة التحقق.",
      "Complete windows, reproducible identities and availability times.",
    ],
    [
      "هندسة السمات",
      "Feature engineering",
      "سمات من لقطة مجمّدة، دون معلومات مستقبلية.",
      "Features from a frozen snapshot, without future information.",
    ],
    [
      "نمو التغطية خلال 24 ساعة",
      "24-hour coverage surge forecasting",
      "لحدث معروف بالفعل؛ قد يستخدم تعلمًا آليًا تقليديًا.",
      "For an already known event; may use conventional ML.",
    ],
    [
      "التحقق الإحصائي",
      "Statistical validation",
      "خطوط أساس، تقييم زمني مستقبلي، معايرة وفائدة تحريرية.",
      "Baselines, prospective temporal evaluation, calibration and editorial utility.",
    ],
    [
      "دعم تنبؤي اختياري",
      "Optional predictive decision support",
      "غير مؤهل للإنتاج؛ حالة البحث HOLD حتى اجتياز البوابات.",
      "Not production-qualified; research remains HOLD until gates pass.",
    ],
  ];
  const flow = (items, research = false) =>
    `<section class="${research ? "research-flow" : ""}"><h2 style="margin-bottom:18px">${research ? L("فرع بحثي مستقل · RESEARCH", "Separate research branch · RESEARCH") : L("مسار الرصد المقصود · OBSERVED", "Intended observed lane · OBSERVED")}</h2>${items.map((r, i) => `<div class="pipeline-step"><h3><b class="step-num">0${i + 1}</b>${L(r[0], r[1])}</h3><span>${L(r[2], r[3])}</span></div>`).join("")}</section>`;
  return (
    pageHead(
      L("كيف يعمل PULSE", "How PULSE works"),
      L(
        "الرصد يساعد القرار الآن في التصميم؛ التنبؤ مسار مستقل يحتاج تقييمًا علميًا.",
        "Observed support and predictive research have separate qualification paths.",
      ),
    ) +
    notice(
      L(
        "المواصفات v0.2 مقبولة للتخطيط وليست نظامًا منفذًا. جميع البوابات التشغيلية غير مؤهلة، والتنبؤ على HOLD.",
        "The v0.2 specs are accepted for planning, not implemented operations. Operational gates remain unqualified; forecasting is on HOLD.",
      ),
      "neutral",
    ) +
    `<div class="pipeline">${flow(ops)}${flow(research, true)}</div><div class="concepts">${[
      [
        "التغطية الإخبارية",
        "News coverage",
        "مرات نشر ضمن لوحة محددة، لا تمثيل لكل المجتمع.",
        "Publication occurrences in a defined panel, not population representation.",
      ],
      [
        "اهتمام الجمهور",
        "Audience attention",
        "قياس منفصل من مصادر مرخصة؛ لا يُستنتج من عدد المقالات.",
        "Separate measurement from licensed sources; not inferred from article counts.",
      ],
      [
        "الرأي العام",
        "Public opinion",
        "بحث تمثيلي بإطار معاينة معلن؛ التغطية والبحث لا يقيسانه.",
        "Representative research with a declared sampling frame; coverage and search cannot measure it.",
      ],
    ]
      .map((r) =>
        panel(
          L(r[0], r[1]),
          `<div class="panel-body"><p>${L(r[2], r[3])}</p></div>`,
        ),
      )
      .join(
        "",
      )}</div><div style="margin-top:20px">${panel(L("أين يساهم الذكاء الاصطناعي؟", "Where does AI contribute?"), `<div class="panel-body"><p class="small muted">${L("مطابقة المعنى العربي، تحديد الأحداث، تحليل التكرار وإعادة النشر، وصياغة شرح منظم مرتبط بالأدلة. تُراجع المخرجات ولا تملك النماذج صلاحية كتابة مميزة أو أدوات شبكة. التنبؤ الإحصائي قد يعتمد على نماذج تقليدية؛ السرد اللغوي ليس بديلًا عن القياس.", "Arabic semantic matching, event identification, duplicate/syndication analysis and structured evidence-bound explanations. Outputs are reviewed; models have no privileged writes or network tools. Forecasting may use conventional statistical ML; narrative is not a substitute for measurement.")}</p></div>`)}</div>`
  );
}
const demoSteps = [
  [
    "overview",
    "اكتشف تطورًا ناشئًا",
    "Discover an emerging event",
    "ابدأ بتجربة الحافلات. قارن اتساع النشر بأصول التقارير؛ ليست كل إعادة نشر دليلًا جديدًا.",
    "Start with the shuttle scenario. Compare publisher breadth with reporting origins; a reprint is not new evidence.",
  ],
  [
    "event",
    "افحص التغطية والأدلة",
    "Inspect coverage and evidence",
    "جرّب فترات الرصد ثم اقرأ النسب وحدود كل ملاحظة. لا يوجد تأكيد لتاريخ التشغيل.",
    "Try the timeline ranges, then read lineage and evidence limits. The launch date is unconfirmed.",
  ],
  [
    "event",
    "حدد زاوية تضيف قيمة",
    "Identify an editorial opportunity",
    "هل يمكن لتقرير خدمي أن يوضح التواتر والأجرة؟ المخرج التوضيحي يطرح سؤالًا؛ لا يقرر عنك.",
    "Could a service explainer clarify frequency and fares? The support output poses a question; you decide.",
  ],
  [
    "workspace",
    "أسند أو تابع",
    "Assign or monitor",
    "جرّب إسناد بطاقة النقل من قسم المراجعة. شاهد انتقالها وسجل النشاط؛ يمكنك أيضًا طلب التحقق.",
    "Assign the transport card from Review. Watch it move and inspect activity; you can also request verification.",
  ],
  [
    "forecast",
    "استكشف البحث المستقبلي",
    "Explore the forecasting concept",
    "أظهر خط الزخم البسيط. الهدف الأولي نمو التغطية خلال 24 ساعة، وليس الرأي العام؛ لا نموذج مُتحقق منه.",
    "Show the momentum baseline. The initial target is 24-hour coverage growth, not public opinion; no validated model is connected.",
  ],
  [
    "how",
    "افهم المعمارية والحدود",
    "Understand architecture and boundaries",
    "اتبع مسار الرصد ثم الفرع البحثي. النموذج لا يتنبأ بوقوع حادث مجهول؛ البوابات مستقلة.",
    "Follow the observed lane and research branch. The model does not predict an unknown incident; qualification gates are separate.",
  ],
];
function demoView() {
  if (state.demo === null) return "";
  const s = demoSteps[state.demo];
  return `<div class="demo-steps" aria-hidden="true">${demoSteps.map((_, i) => `<i class="${i <= state.demo ? "done" : ""}"></i>`).join("")}</div><div class="demo-copy"><strong>${state.demo + 1}/6 · ${L(s[1], s[2])}</strong><p>${L(s[3], s[4])}</p></div><div class="demo-controls">${btn(L("السابق", "Back"), "demo-back", state.demo === 0 ? "disabled" : "")}${btn(state.demo === 5 ? L("إنهاء العرض", "Finish") : L("التالي", "Next"), "demo-next", "", "primary")}${btn(L("خروج", "Exit"), "demo-exit")}</div>`;
}
function render() {
  document.documentElement.lang = state.lang;
  document.documentElement.dir = state.lang === "ar" ? "rtl" : "ltr";
  $("sidebar").innerHTML = sidebar();
  $("topbar").innerHTML = topbar();
  $("demo").innerHTML = demoView();
  const views = {
    overview: () => overview(),
    emerging: () => overview(true),
    event: eventView,
    workspace,
    forecast,
    health,
    how,
  };
  $("main").innerHTML = views[state.view]();
  $("footer").innerHTML =
    icon("help") +
    `<span>${L("جميع الأحداث والمصادر خيالية. التغطية لا تقيس اهتمام الجمهور أو الرأي العام.", "All developments and sources are fictional. Coverage does not measure audience attention or public opinion.")} · ${btn(L("إعادة ضبط العرض", "Reset Demo"), "reset")}</span>`;
}
function updateMain() {
  const views = {
    overview: () => overview(),
    emerging: () => overview(true),
    event: eventView,
    workspace,
    forecast,
    health,
    how,
  };
  $("main").innerHTML = views[state.view]();
}
function applyAction(action, eventId, detail = null) {
  const w = state.workflows[eventId];
  const target = {
    assign: "assigned",
    verify: "verify",
    watch: "watch",
    snooze: "snoozed",
    dismiss: "dismissed",
    covered: "covered",
    restore: "new",
  }[action];
  if (w.status === target && (action !== "assign" || w.editor === detail)) {
    toast(L("هذا الإجراء مسجّل بالفعل", "This action is already recorded"));
    return;
  }
  w.status = target;
  w.editor = action === "assign" ? detail : null;
  w.deadline = action === "snooze" ? Date.now() + Number(detail) * 60000 : null;
  addActivity(action, eventId, detail);
  render();
  toast(L("تم تسجيل الإجراء: ", "Action recorded: ") + tx(actionNames[action]));
}
function openActionDialog(action, eventId) {
  const d = $("action-dialog");
  returnFocus = document.activeElement;
  d.dataset.action = action;
  d.dataset.event = eventId;
  $("dialog-title").textContent = tx(actionNames[action]);
  $("dialog-context").textContent = tx(eventById(eventId).title);
  $("dialog-label").textContent =
    action === "assign"
      ? L("اختر المحرر", "Choose an editor")
      : L("مدة التأجيل (ساعة الجلسة)", "Snooze duration (session clock)");
  $("action-choice").innerHTML =
    action === "assign"
      ? Object.entries(editors)
          .map(([id, v]) => `<option value="${id}">${tx(v)}</option>`)
          .join("")
      : [
          ["30", L("30 دقيقة", "30 minutes")],
          ["120", L("ساعتان", "2 hours")],
          ["1440", L("يوم واحد", "1 day")],
        ]
          .map(([id, t]) => `<option value="${id}">${t}</option>`)
          .join("");
  $("cancel-dialog").textContent = L("إلغاء", "Cancel");
  $("confirm-dialog").textContent = L("تأكيد", "Confirm");
  d.showModal();
  $("action-choice").focus();
}
function demoGo(index) {
  state.demo = index;
  state.selected = "transport";
  state.view = demoSteps[index][0];
  state.query = "";
  state.beat = "all";
  state.filter = "all";
  state.horizon = 24;
  render();
  window.scrollTo({ top: 0, behavior: "instant" });
  const next = document.querySelector('[data-cmd="demo-next"]');
  if (next) next.focus({ preventScroll: true });
}
function inspectBar(target) {
  $("chart-inspect").textContent =
    target.dataset.chartLabel +
    " · " +
    target.dataset.chartValue +
    " " +
    L("مقالات مرصودة خيالية", "fictional observed articles");
}
document.addEventListener("click", (event) => {
  const bar = event.target.closest("[data-chart-index]");
  if (bar) {
    inspectBar(bar);
    return;
  }
  const b = event.target.closest("[data-cmd]");
  if (!b) return;
  const cmd = b.dataset.cmd;
  switch (cmd) {
    case "nav":
      state.query = "";
      state.filter = "all";
      navigate(b.dataset.view);
      break;
    case "open":
      state.selected = b.dataset.event;
      state.range = 6;
      navigate("event");
      break;
    case "language":
      state.lang = state.lang === "ar" ? "en" : "ar";
      render();
      break;
    case "beat":
      state.beat = b.dataset.beat;
      updateMain();
      break;
    case "clear":
      state.beat = "all";
      state.filter = "all";
      state.query = "";
      render();
      break;
    case "range":
      state.range = Number(b.dataset.range);
      updateMain();
      break;
    case "horizon":
      state.horizon = Number(b.dataset.horizon);
      updateMain();
      break;
    case "action":
      if (["assign", "snooze"].includes(b.dataset.action))
        openActionDialog(b.dataset.action, b.dataset.event);
      else applyAction(b.dataset.action, b.dataset.event);
      break;
    case "cancel-dialog":
      $("action-dialog").close();
      break;
    case "reset": {
      const lang = state.lang;
      state = initialState(lang);
      render();
      toast(
        L(
          "أُعيد العرض إلى حالته الأصلية",
          "Demo restored to its initial state",
        ),
      );
      break;
    }
    case "demo-start":
      demoGo(0);
      break;
    case "demo-back":
      demoGo(Math.max(0, state.demo - 1));
      break;
    case "demo-next":
      if (state.demo < 5) demoGo(state.demo + 1);
      else {
        state.demo = null;
        render();
        toast(L("اكتمل العرض الموجّه", "Guided demo complete"));
      }
      break;
    case "demo-exit":
      state.demo = null;
      render();
      break;
  }
});
document.addEventListener("input", (event) => {
  if (event.target.id === "search") {
    state.query = event.target.value;
    if (!["overview", "emerging", "workspace"].includes(state.view)) {
      state.view = "emerging";
      state.filter = "all";
      $("sidebar").innerHTML = sidebar();
    }
    updateMain();
  }
});
document.addEventListener("change", (event) => {
  const t = event.target;
  if (t.id === "status-filter") {
    state.filter = t.value;
    updateMain();
  }
  if (t.id === "event-select") {
    state.selected = t.value;
    updateMain();
  }
  if (t.id === "baseline") {
    state.baseline = t.checked;
    updateMain();
  }
  if (t.dataset.source) {
    const s = sourceById(t.dataset.source);
    if (s.health === t.value) return;
    s.health = t.value;
    s.gap = true;
    s.complete = false;
    addActivity("health", null, { source: s.id, health: s.health });
    render();
    toast(
      L(
        "تغيرت الحالة؛ الملاحظات التاريخية محفوظة",
        "Health updated; historical observations retained",
      ),
    );
  }
});
document.addEventListener("keydown", (event) => {
  const bar = event.target.closest("[data-chart-index]");
  if (bar && ["Enter", " "].includes(event.key)) {
    event.preventDefault();
    inspectBar(bar);
  }
  if (
    event.key === "Escape" &&
    state.demo !== null &&
    !$("action-dialog").open
  ) {
    state.demo = null;
    render();
  }
});
document.addEventListener("focusin", (event) => {
  if (event.target.dataset.chartIndex) inspectBar(event.target);
});
$("action-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const d = $("action-dialog");
  const { action, event: eventId } = d.dataset;
  const detail = $("action-choice").value;
  d.close();
  applyAction(action, eventId, detail);
  const focus =
    document.querySelector(`[data-cmd="open"][data-event="${eventId}"]`) ||
    document.querySelector('[data-cmd="demo-next"]') ||
    $("main");
  focus.focus({ preventScroll: true });
});
$("action-dialog").addEventListener("close", () => {
  if (returnFocus?.isConnected) returnFocus.focus();
});
setInterval(() => {
  let changed = false;
  for (const e of PULSE_DATA.events) {
    const w = workflow(e);
    if (w.status === "snoozed" && w.deadline <= Date.now()) {
      w.status = "watch";
      w.deadline = null;
      addActivity("resume", e.id);
      changed = true;
    }
  }
  if (changed) {
    render();
    toast(
      L(
        "انتهى التأجيل؛ انتقل الحدث إلى المتابعة",
        "Snooze expired; event moved to Watching",
      ),
    );
  }
}, 10000);
render();
