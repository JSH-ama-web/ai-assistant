/* 운동 기록 AI 비서 — 바닐라 JS (프레임워크 없음) */
(() => {
  "use strict";

  const API = ((window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) || "http://localhost:8000").replace(/\/$/, "");
  const UNIT = "분";
  const PAGE = 30;

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  const state = {
    data: [],            // 날짜 오름차순
    summary: null,
    stats: null,
    conversations: [],
    currentConvId: null,
    editingId: null,
    shown: PAGE,
    sending: false,
  };

  /* ── 공통: API 호출 ─────────────────────────────── */
  async function api(path, { method = "GET", body, timeout = 60000 } = {}) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(API + path, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
      const isJson = (res.headers.get("content-type") || "").includes("json");
      const payload = isJson ? await res.json() : null;
      if (!res.ok) throw new Error(errorText(payload) || `요청 실패 (${res.status})`);
      return payload;
    } catch (e) {
      if (e.name === "AbortError") throw new Error("응답 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.");
      if (e instanceof TypeError) throw new Error("서버에 연결할 수 없어요. (서버 기동 중이거나 CORS 설정 확인)");
      throw e;
    } finally {
      clearTimeout(t);
    }
  }
  function errorText(p) {
    if (!p || !p.detail) return "";
    if (typeof p.detail === "string") return p.detail;
    if (Array.isArray(p.detail)) return p.detail.map(d => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join(", ");
    return "";
  }

  function toast(msg, isError = false) {
    const el = $("#toast");
    el.textContent = msg;
    el.className = "toast show" + (isError ? " error" : "");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (el.className = "toast"), 2600);
  }
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = n => (n == null ? "—" : Number(n).toLocaleString("ko-KR", { maximumFractionDigits: 1 }));

  /* ── 콜드 스타트 대응 ───────────────────────────── */
  async function wakeServer() {
    const banner = $("#banner");
    const slow = setTimeout(() => {
      banner.hidden = false;
      banner.textContent = "서버를 깨우는 중이에요. 무료 서버(Render)는 한동안 쉬면 첫 접속에 30~60초 걸릴 수 있어요…";
    }, 2500);
    for (let i = 0; i < 6; i++) {
      try {
        await api("/health", { timeout: 20000 });
        clearTimeout(slow);
        banner.hidden = true;
        return true;
      } catch { /* 재시도 */ }
    }
    clearTimeout(slow);
    banner.hidden = false;
    banner.textContent = "서버에 연결하지 못했어요. 잠시 후 새로고침해 주세요.";
    return false;
  }

  /* ── 다크 모드 ──────────────────────────────────── */
  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem("theme"); } catch { }
    if (saved) document.documentElement.dataset.theme = saved;
    syncThemeIcon();
    $("#themeToggle").addEventListener("click", () => {
      const dark = isDark();
      const next = dark ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch { }
      syncThemeIcon();
      drawChart();
    });
  }
  function isDark() {
    const t = document.documentElement.dataset.theme;
    return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function syncThemeIcon() { $("#themeToggle").textContent = isDark() ? "☀" : "☾"; }

  /* ── 모바일 탭 ──────────────────────────────────── */
  function initTabs() {
    const show = view => {
      $$(".tab").forEach(t => t.classList.toggle("active", t.dataset.view === view));
      $$("[data-panel]").forEach(p => p.classList.toggle("show", p.dataset.panel === view));
      if (view === "data") drawChart();
    };
    $$(".tab").forEach(t => t.addEventListener("click", () => show(t.dataset.view)));
    show("chat");
  }

  /* ── 요약 / 통계 ────────────────────────────────── */
  async function loadSummary() {
    try {
      const [summary, stats] = await Promise.all([api("/api/data/summary"), api("/api/data/statistics")]);
      state.summary = summary;
      state.stats = stats;
      renderSummary();
      drawChart();
    } catch (e) {
      $("#summaryStrip").textContent = "요약을 불러오지 못했어요: " + e.message;
    }
  }

  function renderSummary() {
    const s = state.summary;
    const m = s && s.metrics;
    const badge = $("#trendBadge");
    const trend = s ? s.trend : "—";
    badge.textContent = trend.split(" (")[0];
    badge.className = "badge" + (trend.startsWith("상승") ? " up" : trend.startsWith("하락") ? " down" : "");

    $("#summaryStrip").innerHTML = m
      ? `AI가 참고하는 요약 · <b>${esc(s.period)}</b> · <b>${s.count}</b>개 · 평균 <b>${fmt(m.average)}${UNIT}</b> · 추세 <b>${esc(trend)}</b>`
      : "아직 데이터가 없어요. 오른쪽(모바일: 데이터 탭)에서 추가해 보세요.";

    $("#summaryGrid").innerHTML = m ? `
      <div class="span2"><dt>기간</dt><dd class="mono">${esc(s.period)}</dd></div>
      <div><dt>개수</dt><dd>${s.count}<small>개</small></dd></div>
      <div><dt>평균</dt><dd>${fmt(m.average)}<small>${UNIT}</small></dd></div>
      <div><dt>최대</dt><dd>${fmt(m.max)}<small>${UNIT} · ${esc(m.max_date)}</small></dd></div>
      <div><dt>합계</dt><dd>${fmt(m.total)}<small>${UNIT}</small></dd></div>
      <div class="span2"><dt>최근 추세</dt><dd>${esc(trend)}</dd></div>` : `<div class="span2"><dd>데이터 없음</dd></div>`;

    const st = state.stats;
    if (st && st.count) {
      const wk = Object.entries(st.weekday_average).sort((a, b) => b[1] - a[1])[0];
      const top = st.top_memos.find(t => t.memo !== "휴식") || st.top_memos[0];
      $("#extraStats").innerHTML = `
        <div><dt>중앙값</dt><dd>${fmt(st.median)}${UNIT}</dd></div>
        <div><dt>최장 연속</dt><dd>${st.longest_streak}일</dd></div>
        <div><dt>최다 요일</dt><dd>${wk ? `${wk[0]} ${fmt(wk[1])}` : "—"}</dd></div>
        <div><dt>표준편차</dt><dd>${fmt(st.std)}</dd></div>
        <div><dt>활동일 비율</dt><dd>${Math.round((st.active_ratio || 0) * 100)}%</dd></div>
        <div><dt>최다 종목</dt><dd>${top ? esc(top.memo) : "—"}</dd></div>`;
    } else {
      $("#extraStats").innerHTML = "";
    }
  }

  /* ── 그래프 (SVG 직접 그림) ─────────────────────── */
  function drawChart() {
    const box = $("#chart");
    const pts = (state.stats && state.stats.moving_average_7) || [];
    if (!box.clientWidth) return;
    if (pts.length < 2) { box.innerHTML = `<p class="empty-note">그래프를 그릴 데이터가 부족해요.</p>`; return; }

    const W = box.clientWidth, H = box.clientHeight, P = { l: 30, r: 6, t: 8, b: 20 };
    const maxV = Math.max(...pts.map(p => p.value), 1);
    const yMax = Math.ceil(maxV / 30) * 30;
    const x = i => P.l + (i / (pts.length - 1)) * (W - P.l - P.r);
    const y = v => P.t + (1 - v / yMax) * (H - P.t - P.b);
    const line = key => pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join("");

    const yTicks = [0, yMax / 2, yMax];
    const months = [];
    pts.forEach((p, i) => {
      const m = p.date.slice(0, 7);
      const last = months[months.length - 1];
      if (last && last.m === m) return;
      if (last && x(i) - x(last.i) < 30) months.pop();   // 너무 가까운 라벨(짧은 첫 달)은 생략
      months.push({ m, i });
    });

    box.innerHTML = `
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        ${yTicks.map(t => `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--line)" stroke-width="1"/>
          <text x="${P.l - 6}" y="${y(t) + 4}" text-anchor="end" font-size="10" fill="var(--ink-2)">${t}</text>`).join("")}
        ${months.map(({ m, i }) => `<text x="${x(i)}" y="${H - 4}" font-size="10" fill="var(--ink-2)">${+m.slice(5)}월</text>`).join("")}
        <path d="${line("value")}" fill="none" stroke="var(--chart-raw)" stroke-width="1"/>
        <path d="${line("ma7")}" fill="none" stroke="var(--chart-ma)" stroke-width="2.2" stroke-linejoin="round"/>
        <line id="hoverLine" y1="${P.t}" y2="${H - P.b}" stroke="var(--ink-2)" stroke-dasharray="3 3" visibility="hidden"/>
        <circle id="hoverDot" r="3.5" fill="var(--chart-ma)" visibility="hidden"/>
      </svg><div class="tip" hidden></div>`;

    const svg = $("svg", box), tip = $(".tip", box), hl = $("#hoverLine", box), hd = $("#hoverDot", box);
    const move = ev => {
      const r = svg.getBoundingClientRect();
      const px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
      const i = Math.max(0, Math.min(pts.length - 1, Math.round(((px - P.l) / (W - P.l - P.r)) * (pts.length - 1))));
      const p = pts[i];
      hl.setAttribute("x1", x(i)); hl.setAttribute("x2", x(i)); hl.setAttribute("visibility", "visible");
      hd.setAttribute("cx", x(i)); hd.setAttribute("cy", y(p.ma7)); hd.setAttribute("visibility", "visible");
      tip.hidden = false;
      tip.style.left = `${Math.min(Math.max(x(i), 60), W - 60)}px`;
      tip.style.top = `${y(Math.max(p.value, p.ma7))}px`;
      tip.textContent = `${p.date} · ${fmt(p.value)}${UNIT} (7일 ${fmt(p.ma7)})`;
    };
    const leave = () => { tip.hidden = true; hl.setAttribute("visibility", "hidden"); hd.setAttribute("visibility", "hidden"); };
    svg.addEventListener("mousemove", move);
    svg.addEventListener("touchmove", move, { passive: true });
    svg.addEventListener("mouseleave", leave);
  }
  window.addEventListener("resize", () => { clearTimeout(drawChart._t); drawChart._t = setTimeout(drawChart, 150); });

  /* ── 데이터 CRUD ───────────────────────────────── */
  async function loadData() {
    try {
      state.data = await api("/api/data");
      renderTable();
    } catch (e) {
      $("#dataBody").innerHTML = `<tr><td colspan="4" class="empty-note">${esc(e.message)}</td></tr>`;
    }
  }

  function renderTable() {
    const rows = [...state.data].reverse().slice(0, state.shown);
    $("#dataCount").textContent = `(${state.data.length})`;
    $("#dataBody").innerHTML = rows.length ? rows.map(d => `
      <tr data-id="${esc(d.id)}" class="${d.id === state.editingId ? "editing" : ""}">
        <td class="mono">${esc(d.date)}</td>
        <td class="num">${fmt(d.value)}</td>
        <td>${esc(d.memo)}</td>
        <td class="row-actions">
          <button data-act="edit">수정</button><button data-act="del" class="danger">삭제</button>
        </td>
      </tr>`).join("") : `<tr><td colspan="4" class="empty-note">데이터가 없어요.</td></tr>`;
    $("#moreBtn").hidden = state.data.length <= state.shown;
  }

  function resetForm() {
    state.editingId = null;
    $("#dataForm").reset();
    $("#fDate").value = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
    $("#formTitle").textContent = "데이터 추가";
    $("#saveBtn").textContent = "추가";
    $("#cancelEdit").hidden = true;
    renderTable();
  }

  function startEdit(id) {
    const d = state.data.find(x => x.id === id);
    if (!d) return;
    state.editingId = id;
    $("#fDate").value = d.date;
    $("#fValue").value = d.value;
    $("#fMemo").value = d.memo || "";
    $("#formTitle").textContent = "데이터 수정";
    $("#saveBtn").textContent = "수정 저장";
    $("#cancelEdit").hidden = false;
    renderTable();
    $("#fValue").focus();
  }

  async function submitData(ev) {
    ev.preventDefault();
    const value = Number($("#fValue").value);
    const body = { date: $("#fDate").value, value, memo: $("#fMemo").value.trim() };
    if (!body.date || !Number.isFinite(value) || value < 0) return toast("날짜와 0 이상의 값을 입력하세요.", true);
    const btn = $("#saveBtn");
    btn.disabled = true;
    try {
      if (state.editingId) {
        await api(`/api/data/${encodeURIComponent(state.editingId)}`, { method: "PUT", body });
        toast(`${body.date} 기록을 수정했어요.`);
      } else {
        await api("/api/data", { method: "POST", body });
        toast(`${body.date} · ${fmt(value)}${UNIT} 저장 완료`);
      }
      await Promise.all([loadData(), loadSummary()]);
      resetForm();
    } catch (e) {
      toast(e.message, true);
    } finally {
      btn.disabled = false;
    }
  }

  async function deleteData(id) {
    const d = state.data.find(x => x.id === id);
    if (!d || !confirm(`${d.date} (${fmt(d.value)}${UNIT}) 기록을 삭제할까요?`)) return;
    try {
      await api(`/api/data/${encodeURIComponent(id)}`, { method: "DELETE" });
      toast("삭제했어요.");
      if (state.editingId === id) resetForm();
      await Promise.all([loadData(), loadSummary()]);
    } catch (e) {
      toast(e.message, true);
    }
  }

  function exportData(kind) {
    if (!state.data.length) return toast("내보낼 데이터가 없어요.", true);
    const rows = state.data.map(({ date, value, memo }) => ({ date, value, memo }));
    let blob, name;
    if (kind === "json") {
      blob = new Blob([JSON.stringify(rows, null, 2)], { type: "application/json" });
      name = "workout_data.json";
    } else {
      const q = s => /[",\n]/.test(s) ? `"${String(s).replace(/"/g, '""')}"` : s;
      const csv = "date,value,memo\n" + rows.map(r => [r.date, r.value, q(r.memo || "")].join(",")).join("\n");
      blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }); // BOM: 엑셀 한글 깨짐 방지
      name = "workout_data.csv";
    }
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  /* ── 대화 기록 ─────────────────────────────────── */
  async function loadConversations() {
    try {
      state.conversations = await api("/api/conversations");
      renderConversations();
    } catch (e) {
      $("#convList").innerHTML = `<li class="empty-note">${esc(e.message)}</li>`;
    }
  }

  function renderConversations() {
    const list = state.conversations;
    $("#convList").innerHTML = list.length ? list.map(c => `
      <li class="conv-item ${c.id === state.currentConvId ? "active" : ""}" data-id="${esc(c.id)}" tabindex="0">
        <div class="meta">
          <div class="title">${esc(c.title)}</div>
          <div class="preview">${esc(c.preview)} · ${c.message_count}개</div>
        </div>
        <button class="del" data-act="del" aria-label="대화 삭제" title="삭제">×</button>
      </li>`).join("") : `<li class="empty-note">저장된 대화가 없어요.</li>`;
  }

  async function openConversation(id) {
    try {
      const conv = await api(`/api/conversations/${encodeURIComponent(id)}`);
      state.currentConvId = conv.id;
      const box = $("#messages");
      box.innerHTML = "";
      conv.messages.forEach(m => addMessage(m.role, m.content, m.tool_calls || []));
      renderConversations();
      if (matchMedia("(max-width: 860px)").matches) $('.tab[data-view="chat"]').click();
      toast(`'${conv.title}' 대화를 불러왔어요.`);
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function deleteConversation(id) {
    if (!confirm("이 대화를 삭제할까요?")) return;
    try {
      await api(`/api/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
      if (state.currentConvId === id) newChat();
      await loadConversations();
      toast("대화를 삭제했어요.");
    } catch (e) {
      toast(e.message, true);
    }
  }

  function newChat() {
    state.currentConvId = null;
    $("#messages").innerHTML = $("#emptyTpl").innerHTML;
    renderConversations();
    $("#chatInput").focus();
  }

  /* ── 채팅 ───────────────────────────────────────── */
  function addMessage(role, text, toolCalls = []) {
    const box = $("#messages");
    $(".empty-chat", box)?.remove();
    const el = document.createElement("div");
    el.className = `msg ${role}`;
    el.innerHTML = `<div class="bubble"></div>`;
    // 텍스트는 먼저 이스케이프한 뒤 **굵게** 만 <strong> 으로 바꾼다 (XSS 방지)
    $(".bubble", el).innerHTML = esc(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    if (toolCalls.length) {
      const tc = document.createElement("div");
      tc.className = "tool-calls";
      tc.innerHTML = toolCalls.map(t => {
        const args = Object.entries(t.arguments || {}).map(([k, v]) => `${k}=${v}`).join(", ");
        return `<div class="tool-call">🔧 <code>${esc(t.name)}</code>${args ? ` (${esc(args)})` : ""}${t.reason ? ` — ${esc(t.reason)}` : ""}</div>`;
      }).join("");
      el.prepend(tc);
    }
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
    return el;
  }

  function showTyping() {
    const el = document.createElement("div");
    el.className = "msg assistant";
    el.innerHTML = `<div class="bubble typing" aria-label="답변 생성 중"><i></i><i></i><i></i></div>
      <span class="loading-note">데이터 요약을 확인하고 답변을 만드는 중…</span>`;
    $("#messages").appendChild(el);
    $("#messages").scrollTop = $("#messages").scrollHeight;
    const slow = setTimeout(() => {
      const n = $(".loading-note", el);
      if (n) n.textContent = "서버가 깨어나는 중일 수 있어요. 조금만 기다려 주세요…";
    }, 8000);
    return () => { clearTimeout(slow); el.remove(); };
  }

  async function sendMessage(text) {
    text = text.trim();
    if (!text || state.sending) return;
    state.sending = true;
    $("#sendBtn").disabled = true;
    addMessage("user", text);
    $("#chatInput").value = "";
    autoGrow();
    const stop = showTyping();
    try {
      const res = await api("/api/chat", {
        method: "POST",
        timeout: 90000,
        body: { message: text, conversation_id: state.currentConvId, use_tools: $("#useTools").checked },
      });
      stop();
      addMessage("assistant", res.reply, res.tool_calls || []);
      state.currentConvId = res.conversation_id;
      loadConversations();
    } catch (e) {
      stop();
      addMessage("assistant error", "⚠ " + e.message);
    } finally {
      state.sending = false;
      $("#sendBtn").disabled = false;
      $("#chatInput").focus();
    }
  }

  function autoGrow() {
    const ta = $("#chatInput");
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }

  /* ── 이벤트 연결 ────────────────────────────────── */
  function bind() {
    // 빈 채팅 화면 템플릿 보관 (새 대화 시 복원)
    const tpl = document.createElement("template");
    tpl.id = "emptyTpl";
    tpl.innerHTML = $("#messages").innerHTML;
    document.body.appendChild(tpl);

    $("#chatForm").addEventListener("submit", e => { e.preventDefault(); sendMessage($("#chatInput").value); });
    $("#chatInput").addEventListener("keydown", e => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendMessage(e.target.value); }
    });
    $("#chatInput").addEventListener("input", autoGrow);
    $("#messages").addEventListener("click", e => {
      const s = e.target.closest(".suggest");
      if (s) sendMessage(s.textContent);
    });

    $("#newChat").addEventListener("click", newChat);
    $("#convList").addEventListener("click", e => {
      const item = e.target.closest(".conv-item");
      if (!item) return;
      if (e.target.closest("[data-act=del]")) deleteConversation(item.dataset.id);
      else openConversation(item.dataset.id);
    });
    $("#convList").addEventListener("keydown", e => {
      const item = e.target.closest(".conv-item");
      if (item && e.key === "Enter") openConversation(item.dataset.id);
    });

    $("#dataForm").addEventListener("submit", submitData);
    $("#cancelEdit").addEventListener("click", resetForm);
    $("#dataBody").addEventListener("click", e => {
      const btn = e.target.closest("button[data-act]");
      if (!btn) return;
      const id = btn.closest("tr").dataset.id;
      btn.dataset.act === "edit" ? startEdit(id) : deleteData(id);
    });
    $("#moreBtn").addEventListener("click", () => { state.shown += PAGE; renderTable(); });
    $$("[data-export]").forEach(b => b.addEventListener("click", () => exportData(b.dataset.export)));
  }

  async function init() {
    initTheme();
    initTabs();
    bind();
    resetForm();
    $("#summaryStrip").textContent = "서버 연결 중…";
    await wakeServer();
    await Promise.all([loadSummary(), loadData(), loadConversations()]);
  }

  init();
})();
