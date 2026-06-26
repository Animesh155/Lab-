// Lab 3 instructor dashboard — vanilla JS, no build step.
//
// Flow:
//   1. Get token from ?token=... or prompt for it.
//   2. Hit GET /api/instructor/state to verify the token works.
//   3. Open /ws/instructor?token=... for live state pushes.
//   4. Render the dashboard from `state` messages; render the event feed
//      from `engine_event` messages.

(() => {
  "use strict";

  // ── Phase order (mirrors engine/state.py) ──────────────────────────
  const PHASE_ORDER = [
    "LOBBY", "BRIEFING", "NORMAL_OPS",
    "INJECT_1_RANSOMWARE", "DISCUSSION_1",
    "INJECT_2_WORKER_RADIO", "DISCUSSION_2",
    "ULTIMATUM", "OUTCOME", "DEBRIEF",
  ];
  const PHASE_LABEL = {
    LOBBY: "LOBBY",
    BRIEFING: "BRIEFING",
    NORMAL_OPS: "NORMAL OPS",
    INJECT_1_RANSOMWARE: "RANSOMWARE LOCK",
    DISCUSSION_1: "DISCUSSION 1 — IT vs OT",
    INJECT_2_WORKER_RADIO: "WORKER RADIO + GAUGE",
    DISCUSSION_2: "DISCUSSION 2 — pressure climbing",
    ULTIMATUM: "ULTIMATUM — voting open",
    OUTCOME: "OUTCOME revealed",
    DEBRIEF: "DEBRIEF",
  };
  const PHASE_HELP = {
    LOBBY: "Wait for student groups to sign in, then advance.",
    BRIEFING: "Read the spec briefing out loud, then advance.",
    NORMAL_OPS: "Let students watch ~30s of live HAI data, then advance to fire the ransomware.",
    INJECT_1_RANSOMWARE: "Lock screen is up. Advance to open DISCUSSION 1 (~10 min of IT vs OT cable-pull debate).",
    DISCUSSION_1: "When groups have settled the cable-pull argument, fire Inject 2.",
    INJECT_2_WORKER_RADIO: "Worker radio + gauge visible to Plant Manager. Advance to DISCUSSION 2.",
    DISCUSSION_2: "Pressure climbing. Advance to ULTIMATUM when groups are ready to vote.",
    ULTIMATUM: "Voting is open. Wait for majorities or break ties manually.",
    OUTCOME: "Outcomes revealed per group. Advance to DEBRIEF.",
    DEBRIEF: "Plant Manager from each group presents and justifies. You close.",
  };
  const ROLE_TAGS = ["PLANT_MANAGER", "OT_ENGINEER", "IT_CYBER_LEAD", "PR"];
  const ROLE_LABEL = {
    PLANT_MANAGER: "Plant Manager",
    OT_ENGINEER:   "OT Engineer",
    IT_CYBER_LEAD: "IT/Cyber Lead",
    PR:            "PR",
  };

  // ── State ──────────────────────────────────────────────────────────
  let token = new URLSearchParams(location.search).get("token") || "";
  let ws = null;
  let lastState = null;
  let phaseStartMs = null;
  const eventFeed = [];   // [{ts, type, payload}]

  // ── DOM ────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const tokenCard = $("token-card");
  const dashboard = $("dashboard");

  // ── Token sign-in flow ─────────────────────────────────────────────
  function showTokenPrompt() {
    tokenCard.hidden = false;
    dashboard.hidden = true;
    $("token-input").focus();
  }
  function showDashboard() {
    tokenCard.hidden = true;
    dashboard.hidden = false;
  }
  $("token-submit").addEventListener("click", () => {
    const t = $("token-input").value.trim();
    if (!t) return;
    token = t;
    // Stash in URL so refresh keeps the session.
    const url = new URL(location);
    url.searchParams.set("token", t);
    history.replaceState({}, "", url);
    start();
  });
  $("token-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("token-submit").click();
  });

  // ── REST helpers ───────────────────────────────────────────────────
  async function instAction(path, opts = {}) {
    const r = await fetch(`${path}?token=${encodeURIComponent(token)}`, {
      method: opts.body ? "POST" : "POST",
      headers: opts.body ? {"content-type": "application/json"} : undefined,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (!r.ok) {
      let detail = r.statusText;
      try { const j = await r.json(); detail = j.detail || detail; } catch {}
      addEvent({type: "error", payload: {action: path, detail}});
    }
    return r;
  }

  async function initialState() {
    const r = await fetch(`/api/instructor/state?token=${encodeURIComponent(token)}`);
    if (r.status === 401) return null;
    if (!r.ok) return null;
    return r.json();
  }

  // ── WebSocket ──────────────────────────────────────────────────────
  function connectWS() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws/instructor?token=${encodeURIComponent(token)}`);

    ws.onopen = () => setConn("ok", "connected");
    ws.onclose = () => {
      setConn("bad", "disconnected");
      setTimeout(connectWS, 2000);
    };
    ws.onerror = () => setConn("bad", "error");
    ws.onmessage = (evt) => {
      let msg;
      try { msg = JSON.parse(evt.data); } catch { return; }
      switch (msg.type) {
        case "state":
          applyState(msg.state);
          break;
        case "engine_event":
          addEvent(msg);
          break;
        case "pong":
          break;
      }
    };
  }

  function setConn(cls, text) {
    const p = $("conn-pill");
    p.className = "pill " + cls;
    p.textContent = text;
  }

  // ── Render: full state ─────────────────────────────────────────────
  function applyState(s) {
    if (!s) return;
    lastState = s;

    // Topbar
    $("session-id").textContent = "session: " + s.session_id;

    // Phase
    const phase = s.phase;
    $("current-phase").textContent = PHASE_LABEL[phase] || phase;
    $("phase-help").textContent = PHASE_HELP[phase] || "";

    // Phase-start tracking for the elapsed clock
    if (s.phase_started_at) {
      phaseStartMs = Date.parse(s.phase_started_at);
    }

    // Advance button
    const idx = PHASE_ORDER.indexOf(phase);
    const next = PHASE_ORDER[idx + 1];
    const advanceBtn = $("advance-btn");
    if (next) {
      advanceBtn.disabled = false;
      $("advance-next").textContent = "→ " + (PHASE_LABEL[next] || next);
    } else {
      advanceBtn.disabled = true;
      $("advance-next").textContent = "(end of scenario)";
    }

    // Inject2 button — only valid in DISCUSSION_1
    $("inject2-btn").disabled = phase !== "DISCUSSION_1";

    // Stats
    const groupCount = Object.keys(s.groups || {}).length;
    $("stat-groups").textContent = groupCount;
    const totalStudents = Object.values(s.connected_students_per_group || {})
      .reduce((a, b) => a + b, 0);
    $("stat-students").textContent = totalStudents;

    // Total votes & outcomes
    let totalA = 0, totalB = 0;
    let outcomeCounts = {shutdown: 0, close_call: 0, rupture: 0};
    for (const g of Object.values(s.groups || {})) {
      const tally = computeTally(g.votes);
      totalA += tally.A;
      totalB += tally.B;
      if (g.outcome) outcomeCounts[g.outcome.result_key] = (outcomeCounts[g.outcome.result_key] || 0) + 1;
    }
    $("stat-votes").textContent = `${totalA} / ${totalB}`;
    const outcomeBits = [];
    if (outcomeCounts.shutdown)   outcomeBits.push(`${outcomeCounts.shutdown}↓`);
    if (outcomeCounts.close_call) outcomeBits.push(`${outcomeCounts.close_call}✓`);
    if (outcomeCounts.rupture)    outcomeBits.push(`${outcomeCounts.rupture}✗`);
    $("stat-outcomes").textContent = outcomeBits.length ? outcomeBits.join(" · ") : "—";

    // Groups
    renderGroups(s);
  }

  function computeTally(votes) {
    const t = {A: 0, B: 0};
    for (const v of Object.values(votes || {})) {
      if (v === "A" || v === "B") t[v]++;
    }
    return t;
  }

  function renderGroups(s) {
    const grid = $("group-grid");
    const groupIds = Object.keys(s.groups || {}).sort();
    if (groupIds.length === 0) {
      grid.innerHTML = '<p class="muted">No students have joined yet. Share the student URL.</p>';
      return;
    }
    grid.innerHTML = "";

    for (const gid of groupIds) {
      const g = s.groups[gid];
      const connected = (s.connected_students_per_group || {})[gid] || 0;
      const tally = computeTally(g.votes);
      const tieDuringUltimatum = (
        s.phase === "ULTIMATUM" &&
        tally.A === tally.B && tally.A + tally.B >= 2 &&
        !g.outcome
      );

      const card = document.createElement("div");
      card.className = "group-card";
      if (g.outcome) card.classList.add("has-outcome");
      if (tieDuringUltimatum) card.classList.add("tie");

      // Header
      const header = document.createElement("div");
      header.className = "group-header";
      header.innerHTML = `
        <h3>${escapeHtml(gid)}</h3>
        <span class="group-count">${connected} connected</span>
      `;
      card.appendChild(header);

      // Role rows
      const roleList = document.createElement("div");
      roleList.className = "role-list";
      const byRole = {};
      for (const st of Object.values(g.students || {})) byRole[st.role] = st;
      for (const role of ROLE_TAGS) {
        const stu = byRole[role];
        const row = document.createElement("div");
        if (!stu) {
          row.className = "role-row empty";
          row.innerHTML = `
            <span class="role-tag">${ROLE_LABEL[role]}</span>
            <span class="display-name">— unfilled —</span>
            <span class="conn-dot"></span>
          `;
        } else {
          const myVote = g.votes ? g.votes[stu.student_id] : null;
          row.className = "role-row" + (stu.connected ? "" : " disconnected");
          row.innerHTML = `
            <span class="role-tag">${ROLE_LABEL[role]}</span>
            <span class="display-name">${escapeHtml(stu.display_name)}</span>
            ${myVote ? `<span class="vote-mark ${myVote}">${myVote}</span>` : `<span class="vote-mark"></span>`}
            <span class="conn-dot"></span>
          `;
        }
        roleList.appendChild(row);
      }
      card.appendChild(roleList);

      // Tally bar (visible during ULTIMATUM / OUTCOME)
      if (["ULTIMATUM", "OUTCOME", "DEBRIEF"].includes(s.phase) || tally.A + tally.B > 0) {
        const total = Math.max(1, tally.A + tally.B);
        const aPct = (tally.A / total) * 100;
        const bPct = (tally.B / total) * 100;
        const tallyRow = document.createElement("div");
        tallyRow.className = "tally-row";
        tallyRow.innerHTML = `
          <div class="tally-bar">
            <div class="tally-a" style="width:${aPct}%"></div>
            <div class="tally-b" style="width:${bPct}%"></div>
          </div>
          <span class="tally-text">A:${tally.A} · B:${tally.B}</span>
        `;
        card.appendChild(tallyRow);
      }

      // Outcome banner
      if (g.outcome) {
        const out = document.createElement("div");
        out.className = "outcome-banner " + g.outcome.result_key;
        const labels = {shutdown: "SHUTDOWN", close_call: "CLOSE CALL", rupture: "TANK RUPTURE"};
        out.innerHTML = `
          <strong>${labels[g.outcome.result_key] || g.outcome.result_key}</strong>
          · $${g.outcome.cost_usd.toLocaleString()}
          · ${g.outcome.casualties} casualties
        `;
        card.appendChild(out);
      }

      // Action buttons
      const actions = document.createElement("div");
      actions.className = "group-actions";
      if (tieDuringUltimatum) {
        actions.innerHTML = `
          <button class="primary" data-act="break_tie" data-gid="${gid}" data-choice="A">Tie-break A</button>
          <button class="danger"  data-act="break_tie" data-gid="${gid}" data-choice="B">Tie-break B</button>
        `;
      }
      actions.innerHTML += `<button class="secondary" data-act="reset" data-gid="${gid}">Reset group</button>`;
      card.appendChild(actions);
      grid.appendChild(card);
    }
  }

  // ── Click delegation for group actions ────────────────────────────
  $("group-grid").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    const gid = btn.dataset.gid;
    if (act === "reset") {
      if (!confirm(`Reset votes/outcome for group ${gid}?`)) return;
      await instAction(`/api/instructor/reset_group/${encodeURIComponent(gid)}`);
    } else if (act === "break_tie") {
      const choice = btn.dataset.choice;
      await instAction("/api/instructor/break_tie", {body: {group_id: gid, choice}});
    }
  });

  // ── Phase controls ────────────────────────────────────────────────
  $("advance-btn").addEventListener("click", async () => {
    await instAction("/api/instructor/advance");
  });
  $("inject2-btn").addEventListener("click", async () => {
    await instAction("/api/instructor/inject2");
  });

  $("reset-session-btn").addEventListener("click", async () => {
    const groups = lastState ? Object.keys(lastState.groups || {}).length : 0;
    const phase = lastState ? lastState.phase : "?";
    const msg = `End the current session?\n\n` +
      `Phase: ${phase}\nGroups: ${groups}\n\n` +
      `This wipes all groups, votes, and outcomes, archives the event log, ` +
      `and rewinds to LOBBY.\n\n` +
      `Type RESET to confirm:`;
    const confirm = prompt(msg);
    if (confirm !== "RESET") return;
    const r = await fetch(`/api/instructor/reset_session?token=${encodeURIComponent(token)}`, {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({confirm: "RESET"}),
    });
    if (!r.ok) {
      let detail = r.statusText;
      try { const j = await r.json(); detail = j.detail || detail; } catch {}
      alert("Reset failed: " + detail);
    }
    // No further action — the WS will push fresh state in a moment.
  });

  // ── Event feed ────────────────────────────────────────────────────
  function addEvent(msg) {
    const ts = new Date().toLocaleTimeString();
    eventFeed.push({ts, type: msg.event || msg.type, payload: msg.payload || {}});
    if (eventFeed.length > 200) eventFeed.shift();
    renderEvents();
  }
  function renderEvents() {
    const feed = $("event-feed");
    feed.innerHTML = "";
    const recent = eventFeed.slice().reverse().slice(0, 60);
    for (const ev of recent) {
      const row = document.createElement("div");
      row.className = "event-row";
      row.innerHTML = `
        <span class="time">${ev.ts}</span>
        <span class="type ${ev.type}">${ev.type}</span>
        <span class="payload">${escapeHtml(summarisePayload(ev.payload))}</span>
      `;
      feed.appendChild(row);
    }
    $("event-count").textContent = `(${eventFeed.length})`;
  }
  function summarisePayload(p) {
    if (!p) return "";
    if (p.group_id && p.role)        return `${p.group_id} · ${p.role} · ${p.display_name || p.student_id || ""}`;
    if (p.group_id && p.choice)      return `${p.group_id} · vote ${p.choice}  (tally A:${p.tally?.A ?? "?"} B:${p.tally?.B ?? "?"})`;
    if (p.group_id && p.outcome)     return `${p.group_id} · ${p.outcome.result_key}`;
    if (p.from && p.to)              return `${p.from} → ${p.to}`;
    if (p.group_id)                  return p.group_id;
    return JSON.stringify(p).slice(0, 100);
  }

  // ── Phase elapsed clock ───────────────────────────────────────────
  setInterval(() => {
    if (!phaseStartMs) return;
    const secs = Math.floor((Date.now() - phaseStartMs) / 1000);
    const mm = String(Math.floor(secs / 60)).padStart(2, "0");
    const ss = String(secs % 60).padStart(2, "0");
    $("time-pill").textContent = `phase ${mm}:${ss}`;
  }, 1000);

  // ── Heartbeat ─────────────────────────────────────────────────────
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({type: "ping"}));
    }
  }, 25000);

  // ── Util ──────────────────────────────────────────────────────────
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  // ── Boot ──────────────────────────────────────────────────────────
  async function start() {
    if (!token) { showTokenPrompt(); return; }
    const s = await initialState();
    if (s === null) { showTokenPrompt(); return; }
    showDashboard();
    applyState(s);
    connectWS();
  }

  start();
})();
