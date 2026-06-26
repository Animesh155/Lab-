// Lab 3 student HMI — vanilla JS, no build step.
//
// Flow:
//   1. Show LOBBY → user picks group + role + name
//   2. Open WebSocket /ws/group/{group_id}, send "join"
//   3. Listen for state_update / pressure_tick / vote_tally messages
//   4. Render the appropriate <section> for current phase

(() => {
  "use strict";

  // ── Sticky student ID (survives reloads) ───────────────────────────
  let studentId = localStorage.getItem("lab3.student_id");
  if (!studentId) {
    studentId = "stu_" + Math.random().toString(36).slice(2, 12);
    localStorage.setItem("lab3.student_id", studentId);
  }

  // ── State ──────────────────────────────────────────────────────────
  let ws = null;
  let currentPhase = "LOBBY";
  let myRole = null;
  let myGroupId = null;
  let myVote = null;

  // ── Role-specific prompts (mirrors phases.yaml) ────────────────────
  const ROLE_PROMPTS = {
    BRIEFING: {
      PLANT_MANAGER: "You own the safety case. Only you can authorize shutdown.",
      OT_ENGINEER:   "You know the process and the PLCs. The HMI was your world.",
      IT_CYBER_LEAD: "Cyber incident responder on shift. Your instinct: contain.",
      PR:            "Communications. You handle the press, customers, regulators.",
    },
    INJECT_1_RANSOMWARE: {
      // The IT-vs-OT cable-pull fight. The Plant Manager listens; the others argue.
      PLANT_MANAGER: "You will hear two arguments in the next minute. Listen to both. The call is yours.",
      OT_ENGINEER:   "If anyone proposes pulling cables — push back. Severing the network may also kill the automated safety valves. Make that case out loud.",
      IT_CYBER_LEAD: "Your training says: isolate now to stop the spread. Argue for pulling the network. You are the person in the room with that instinct — own it.",
      PR:            "Disclosure clock starts the moment we acknowledge an incident. Who knows? Who must know? In what order?",
    },
    DISCUSSION_1: {
      PLANT_MANAGER: "You don't have to follow either side. Name your reasoning.",
      OT_ENGINEER:   "The PLC fieldbus is on the same physical network as the HMI. Cutting cables cuts both. Say so.",
      IT_CYBER_LEAD: "Don't soften your case. If you back off, the room never has the real argument.",
      PR:            "Whatever they decide — what's the one-sentence statement we issue tonight?",
    },
    INJECT_2_WORKER_RADIO: {
      PLANT_MANAGER: "You can see one gauge through the lock screen. Do you trust it?",
      OT_ENGINEER:   "Without the HMI, what telemetry do you actually trust right now?",
      IT_CYBER_LEAD: "The attacker may still be in the network. Could the gauge value be spoofed?",
      PR:            "If we knowingly send a worker into a pressurized zone, how do we explain that decision tomorrow?",
    },
    DISCUSSION_2: {
      PLANT_MANAGER: "Pressure climbing. Vote A or B is coming.",
      OT_ENGINEER:   "What's your read on the trend? What can you not verify?",
      IT_CYBER_LEAD: "Last chance to challenge the gauge reading.",
      PR:            "Draft the statement for either outcome. You won't have time later.",
    },
  };

  // ── Render: show only the section matching current phase ───────────
  function renderPhase(phase) {
    document.querySelectorAll(".screen").forEach((el) => {
      const supported = (el.dataset.phase || "").split(/\s+/);
      el.hidden = !supported.includes(phase);
    });
    document.getElementById("phase-pill").textContent = phase.replace(/_/g, " ");
    currentPhase = phase;

    // Inject role prompt into whichever lock card is active
    if (myRole) {
      const promptText = (ROLE_PROMPTS[phase] || {})[myRole] || "";
      ["briefing-role-prompt", "lock1-role-prompt", "lock2-role-prompt"].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.textContent = promptText;
      });
    }

    // Vote panel only in ULTIMATUM
    const votePanel = document.getElementById("vote-panel");
    if (votePanel) votePanel.hidden = phase !== "ULTIMATUM";
  }

  // ── Render: tailored state from server ─────────────────────────────
  function applyStateUpdate(msg) {
    myRole = msg.your_role || myRole;
    myGroupId = msg.group_id || myGroupId;

    document.getElementById("role-pill").textContent =
      myRole ? myRole.replace(/_/g, " ") : "no role";

    renderPhase(msg.phase);

    // Gauge visibility (Plant Manager during inject2+)
    const gaugeContainer = document.getElementById("gauge-container");
    if (gaugeContainer) gaugeContainer.hidden = !msg.show_gauge;

    // Tally
    if (msg.tally) {
      const a = document.getElementById("tally-a");
      const b = document.getElementById("tally-b");
      if (a) a.textContent = msg.tally.A || 0;
      if (b) b.textContent = msg.tally.B || 0;
    }

    // Outcome (in OUTCOME phase)
    if (msg.outcome) {
      renderOutcome(msg.outcome);
    }

    // Sensors:
    //  - During NORMAL_OPS, real server-side `sensor_tick` messages drive the
    //    tiles. We start the client-side jitter as a fallback so the tiles
    //    show *something* if the server has no HAI dataset loaded.
    //  - In locked phases, frozen_sensors snapshot is shown (the moment ops
    //    went dark).
    if (msg.sensors_streaming) {
      renderPlaceholderSensors();
    } else if (msg.frozen_sensors) {
      writeSensors(msg.frozen_sensors);
    }
  }

  // ── Render: real HAI tick from server ──────────────────────────────
  function applySensorTick(msg) {
    if (!msg.sensors) return;
    // Real data has arrived — kill the placeholder jitter.
    stopPlaceholderSensors();
    writeSensors(msg.sensors);
  }

  function writeSensors(sensors) {
    for (const [id, value] of Object.entries(sensors)) {
      const el = document.getElementById(id);
      if (el) el.textContent = typeof value === "number" ? value.toFixed(2) : value;
    }
  }

  // ── Render: pressure gauge ─────────────────────────────────────────
  function applyPressureTick(msg) {
    if (!myGroupId) return;
    const groupData = msg.groups && msg.groups[myGroupId];
    if (!groupData) return;
    const p = groupData.pressure_bar;

    const valueEl = document.getElementById("gauge-value");
    if (valueEl) valueEl.textContent = p.toFixed(2);

    // Needle: 0 bar = -90°, 8 bar = +90°. Linear map.
    const angle = Math.max(-90, Math.min(90, (p / 8) * 180 - 90));
    const needle = document.getElementById("gauge-needle");
    if (needle) needle.setAttribute("transform", `rotate(${angle} 100 100)`);

    const warn = document.getElementById("gauge-warning");
    if (warn) warn.hidden = !groupData.red_zone;
  }

  // ── Render: vote tally update ──────────────────────────────────────
  function applyVoteTally(msg) {
    const a = document.getElementById("tally-a");
    const b = document.getElementById("tally-b");
    if (a) a.textContent = msg.tally.A || 0;
    if (b) b.textContent = msg.tally.B || 0;
  }

  // ── Render: outcome ────────────────────────────────────────────────
  function renderOutcome(outcome) {
    const card = document.getElementById("outcome-card");
    if (!card) return;
    card.className = "card outcome-card " + outcome.result_key;
    const titles = {
      shutdown: "EMERGENCY SHUTDOWN",
      close_call: "CLOSE CALL — Worker Reached Valve",
      rupture: "TANK RUPTURE",
    };
    document.getElementById("outcome-title").textContent = titles[outcome.result_key] || "Outcome";
    document.getElementById("outcome-narrative").textContent = outcome.narrative;
    document.getElementById("outcome-casualties").textContent = outcome.casualties;
    document.getElementById("outcome-cost").textContent =
      "$" + outcome.cost_usd.toLocaleString();
  }

  // ── Render: fake sensor readings during NORMAL_OPS ─────────────────
  // (Placeholder until HAI is wired — animates so it looks alive.)
  let sensorIntervalId = null;
  function renderPlaceholderSensors() {
    if (sensorIntervalId) return;
    const jitter = (base, range) => (base + (Math.random() - 0.5) * range).toFixed(2);
    const tick = () => {
      const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
      set("s_reactor1_pressure", jitter(1.32, 0.04));
      set("s_reactor1_temp", jitter(78.4, 0.5));
      set("s_feed_flow", jitter(42.1, 0.8));
      set("s_tank_level", jitter(67.0, 1.0));
      set("s_outlet_flow", jitter(40.9, 0.7));
      set("s_pump_a", jitter(1480, 6));
      set("s_pump_b", jitter(1492, 6));
      set("s_valve", jitter(54.0, 0.4));
    };
    tick();
    sensorIntervalId = setInterval(tick, 1500);
  }
  function stopPlaceholderSensors() {
    if (sensorIntervalId) { clearInterval(sensorIntervalId); sensorIntervalId = null; }
  }

  // ── WebSocket ──────────────────────────────────────────────────────
  function connect(groupId, displayName, role) {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws/group/${encodeURIComponent(groupId)}`);

    ws.onopen = () => {
      setConnState("ok", "connected");
      ws.send(JSON.stringify({
        type: "join",
        student_id: studentId,
        display_name: displayName,
        role: role,
      }));
    };

    ws.onmessage = (evt) => {
      let msg;
      try { msg = JSON.parse(evt.data); } catch { return; }
      switch (msg.type) {
        case "state_update":
          if (msg.phase !== "NORMAL_OPS") stopPlaceholderSensors();
          applyStateUpdate(msg);
          break;
        case "pressure_tick":
          applyPressureTick(msg);
          break;
        case "sensor_tick":
          applySensorTick(msg);
          break;
        case "vote_tally":
          applyVoteTally(msg);
          break;
        case "error":
          showJoinError(msg.error || "server error");
          break;
        case "pong":
          break;
        default:
          // Unknown — ignore
      }
    };

    ws.onclose = () => {
      setConnState("bad", "disconnected");
      // Auto-reconnect after 2s if we had a role
      if (myRole && myGroupId) {
        setTimeout(() => connect(myGroupId, displayName, myRole), 2000);
      }
    };

    ws.onerror = () => setConnState("bad", "error");
  }

  function setConnState(cls, text) {
    const pill = document.getElementById("conn-pill");
    pill.className = "status-pill " + cls;
    pill.textContent = text;
  }

  function showJoinError(msg) {
    const el = document.getElementById("join-error");
    el.textContent = msg;
    el.hidden = false;
  }

  // ── Form: join ─────────────────────────────────────────────────────
  document.getElementById("join-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const displayName = fd.get("display_name").trim();
    const groupId = fd.get("group_id");
    const role = fd.get("role");
    if (!displayName) return;
    myGroupId = groupId;
    myRole = role;
    document.getElementById("join-error").hidden = true;
    connect(groupId, displayName, role);
  });

  // ── Vote buttons ───────────────────────────────────────────────────
  document.querySelectorAll(".vote-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      const choice = btn.dataset.choice;
      myVote = choice;
      ws.send(JSON.stringify({ type: "vote", choice: choice }));
      document.querySelectorAll(".vote-btn").forEach((b) =>
        b.classList.toggle("selected", b === btn)
      );
    });
  });

  // ── Init ───────────────────────────────────────────────────────────
  renderPhase("LOBBY");

  // Heartbeat ping every 25s
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 25000);
})();
