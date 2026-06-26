# Lab 3 — The Blind Operator

*A tabletop exercise in OT cybersecurity decision-making*

> **Note (reconstructed).** This is the original AI-polished version of the
> manual, restored from memory for reference after we replaced it with a
> scaffolded version (`LAB_MANUAL.md`). Wording may not be byte-identical
> to the original draft, but the structure, role list, and section flow
> are preserved. Read this as the "before"; read `LAB_MANUAL.md` as the
> "after".

---

## Cover sheet

| Field | Detail |
|---|---|
| Lab | 3 of the OT Security series |
| Format | Group exercise, instructor-led |
| Duration | 60–75 minutes |
| Group size | 5 students per group |
| You will need | A laptop or phone with a modern browser |
| You will not need | Prior OT experience. We will explain every term. |

---

## 1. Learning objectives

By the end of this lab you will be able to:

1. **Describe** the role of a human-machine interface (HMI) in industrial
   plant operations.
2. **Recognise** how a ransomware attack on an HMI degrades operator decision
   quality even when the plant itself is unharmed.
3. **Weigh** production loss against worker safety under uncertainty and
   time pressure.
4. **Discuss** the limits of trusting a single instrument when the broader
   control system is compromised.
5. **Articulate** the difference between IT-style "we can wait this out" and
   OT-style "people and equipment are at stake right now".

There is no single "correct" answer to the dilemma at the heart of this lab.
The objective is the *quality of your reasoning*, not the choice itself.

---

## 2. The scenario in one paragraph

You are operators at **Meridian Chemicals, Plant 4** — a working chemical
reactor that mixes feedstock under pressure. You start the shift on a routine
day. Mid-shift, your control room's HMI is encrypted by ransomware. You can
no longer see your dashboards. The plant *itself* is still running, but you
have lost your eyes. A few minutes later a floor worker calls on the radio:
"the local pressure gauge by Reactor 1 is reading high — I'm walking up to
the manual relief valve, ETA four minutes". You can still see one gauge
through the lock screen. The pressure is climbing. **You have to decide.**

We will not tell you yet what the two options are. You will discover them
inside the simulation.

---

## 3. Roles — pick one before the simulation starts

You will be one of five people in the control room. Each role brings a
different lens to the decision. **Lean into your role** — disagree out loud
when your interests differ from someone else's. That is the point.

### 3.1 Plant Manager
You own the safety case for this plant. Only you can authorise a full
emergency shutdown. You will see *one* gauge through the ransomware lock
screen — none of the other roles will. The buck stops with you.

### 3.2 Operations Lead
You run the day-to-day. The HMI was your world. Without it you have to
reason about plant state from memory, intuition, and what the workers tell
you on the radio. You know production costs in dollars per hour.

### 3.3 Security Engineer
You are the cyber-security responder on shift. Your instinct is to isolate
the attack, but isolation can mean pulling cables and that can have physical
consequences. You also have to think about whether the ransomware could
spread beyond the HMI into the PLCs that actually drive the equipment.

### 3.4 Legal Counsel
You are joining remotely by phone. Your job is regulatory exposure,
disclosure timing, insurance, and — most uncomfortably — the legal posture
if a worker is injured because of a decision made on this call.

### 3.5 Worker Representative
You speak for the people on the plant floor. There is a real human walking
toward a pressurised vessel right now. You know what the workers will and
will not accept. You can also dial the radio at any moment to talk to them.

**Coordinate so each role is filled exactly once per group.** If your group
is smaller than five, leave the role most distant from your strengths
unassigned — the prompts will adapt.

---

## 4. Joining the simulation

1. Open the URL the instructor gave you in your browser. The page is titled
   **"Meridian Chemicals — Plant 4 HMI Console"**.
2. On the sign-in card:
   - Enter your **display name** (visible to your group only).
   - Pick your **group** (the instructor will assign each group a number).
   - Pick your **role**.
3. Click **Sign in**.
4. You will see a **briefing card** while you wait for the rest of your
   group to sign in. Use this time to read your role text on the screen and
   to introduce yourself by name + role to your groupmates.

> **Connection issues?** If the top right says "disconnected", refresh the
> page. Your role is remembered by the browser — you will pick up where you
> left off.

---

## 5. What happens, phase by phase

The instructor advances the simulation through ten phases. You do not need
to memorise the names — the top bar of the HMI always shows the current
phase.

### Phase 1 — LOBBY
You pick your group, role, and display name. *Nothing else happens here.*

### Phase 2 — BRIEFING
A short scenario card. Your role-specific guidance is shown in **italic
yellow** — that is your private prompt for the phase.

### Phase 3 — NORMAL_OPS — "the routine shift"
This is the dashboard you'd see on a normal day. Eight live sensor tiles:

- Reactor Pressure (bar)
- Reactor Temp (°C)
- Intake Flow (L/min)
- Tank Level (mm)
- Outlet Flow (L/min)
- Level Valve / Feed Valve / Pressure Valve (%)

The values are **real industrial data** from a research testbed — they are
not made up. They move in small natural ways. Use this minute to build a
mental model of "what normal looks like" — you will need it later.

> **Exercise during this phase**: Each group member should silently note
> one sensor whose typical range surprises them. Share at the start of the
> next phase if there's time.

### Phase 4 — INJECT_1_RANSOMWARE — "the lock screen"
The HMI glitches and is replaced by a red lock screen demanding
**$2.4 million in Bitcoin within 71 hours**. The plant itself is still
running. You have lost visibility, not control. Your gut reaction is the
right place to start — note it, then move on.

### Phase 5 — DISCUSSION_1 — "the first debate"
The lock screen stays up. Each role's prompt updates. **Five minutes** to
discuss. Some questions worth chewing on:

- Do we pull the network cables right now? What does that cost us?
- What information do we *still* have, that the attacker cannot see?
- How do we know the plant is *actually* fine, vs just *seems* fine?
- Who has authority to halt production? Who has authority to keep it going?
- What do we tell the workers on the floor in the next thirty seconds?

There is no clean answer. Disagree. **Disagree out loud.**

### Phase 6 — INJECT_2_WORKER_RADIO — "the radio call"
A blue notification appears: a worker is on the radio. Read it as a group.
The Plant Manager — and only the Plant Manager — now sees a **single
pressure gauge** below the lock screen. The needle is moving.

Others have to take the Plant Manager's word for what the gauge says. That
is intentional. **In a real incident, information asymmetry is the rule,
not the exception.**

### Phase 7 — DISCUSSION_2 — "the stakes raise"
The needle keeps climbing. You can see it crossing into the yellow zone.
Discuss harder. Some pointed questions:

- Could the gauge value be **spoofed** by the attacker? How would you tell?
- The worker has a four-minute walk to the valve. What happens in those
  four minutes if we do nothing?
- Is "let the worker handle it" courageous, or is it just delegating risk
  to someone with no decision rights?

### Phase 8 — ULTIMATUM — "the vote"
The pressure needle is in the **red zone** (≥ 5 bar). A vote panel appears.
Each member of your group votes:

> **Option A — Emergency Shutdown**
> Vent the reactor through the automatic relief. Halt production. Recall
> the worker immediately. Predictable, expensive, safe.
>
> **Option B — Do Nothing**
> Let the worker reach the manual relief valve. If they get there in time,
> the plant survives the incident and production continues. If they don't,
> the vessel ruptures.

You vote independently. **A strict majority** of your group's connected
members wins. Ties are broken by the instructor.

### Phase 9 — OUTCOME — "the consequence"
The simulation reveals what happened.

- **If your group chose A**: the shutdown completed cleanly. $4.2M
  production loss. Six-week restart. Zero casualties. Same for every group
  that chose A.
- **If your group chose B**: the simulation rolls a weighted die.
  60% chance the worker reaches the valve in time and the close call
  becomes a story. 40% chance the vessel ruptures with two fatalities and
  a plant evacuation. The roll is determined by a per-group seed logged in
  the event log — so your group's result is reproducible for the debrief.

Sit with this. The randomness on Option B is intentional and pedagogical.
Real OT decisions are made under uncertainty. "It worked last time" is not
a safety case.

### Phase 10 — DEBRIEF — "what just happened"
The instructor leads. You will compare outcomes with other groups, identify
patterns, and articulate what your group learned.

---

## 6. The decision — things worth considering

Read this **before** the vote, so it's in your head when the gauge is red.

### Production loss is concrete. Safety risk is probabilistic.
$4.2M is a known number. "Maybe the worker makes it" is not. Humans are
*much* better at comparing two known numbers than at comparing a known
number with a probability. Be deliberate.

### "It worked last time" is not safety.
A near-miss is exactly the same physical event as a disaster, just with a
luckier random variable. If your group is leaning B because the close-call
narrative *sounds reasonable*, ask: what would have to be different about
the next incident for B to be the wrong call?

### The attacker is still in your system.
You do not know whether the gauge value is real. The HMI is encrypted. The
PLCs that drive the gauge are presumably still on the same network. A
sophisticated attacker could spoof the gauge to *force* either choice. How
would you tell?

### Authority is not consensus.
The Plant Manager has the formal authority to shut down. The vote is a
*group* mechanism for this exercise — in real life, the Plant Manager could
act unilaterally and live with the consequences. Discuss whether your group
is exercising authority correctly or hiding behind consensus.

### "Do nothing" is a decision.
Option B is not the absence of a choice. It is the choice to expose a
worker to a pressurised vessel based on a single suspect instrument. Frame
it that way and the moral weight is more honest.

---

## 7. Debrief questions

Your instructor will pick a few of these. Be ready to speak.

1. What information did your group actually have, and what did your group
   *assume*?
2. Did the visibility of the gauge change the decision? Would you have
   chosen the same way without it?
3. If your group picked B and got "close call" — would you do it again?
4. If your group picked A — was anyone tempted by B at any point? What
   would have pushed you over?
5. How did role-play affect the decision? Did the Legal Counsel and the
   Worker Rep push in different directions?
6. What was the most useful question someone asked your group during the
   debate? What did it unlock?
7. What does this exercise teach about the difference between IT-style
   incident response (slow, deliberate, contain-and-eradicate) and OT-style
   incident response (fast, irreversible, safety-first)?

---

## 8. Quick glossary

- **OT** — Operational Technology. The computers that *control* physical
  things: valves, motors, reactors. Opposite of IT.
- **HMI** — Human-Machine Interface. The dashboard the operator stares at.
  Usually a touchscreen or a tile of monitors.
- **PLC** — Programmable Logic Controller. The small, ruggedised industrial
  computer that actually opens and closes the valves. The HMI talks to it.
  In this lab the PLC is unaffected by the ransomware — only the HMI is
  encrypted.
- **Ransomware** — malware that encrypts files and demands payment to
  decrypt them. The 2017 NotPetya outbreak halted real container ports and
  pharmaceutical plants for days. The 2021 Colonial Pipeline ransomware
  halted fuel distribution across the US East Coast. The threat is real.
- **Modbus** — a 1979 industrial protocol that PLCs still speak today.
  Mostly unauthenticated. If you can reach a Modbus device on the network,
  you can usually read or write its registers.
- **Data diode** — a hardware device that physically allows traffic in only
  one direction. Used to isolate OT networks from IT networks. This lab
  series builds toward understanding *why* data diodes exist.
- **Cyber-physical system** — any system where a cyber attack can cause a
  physical consequence. A power grid. A pipeline. The reactor in this lab.

---

## 9. Record sheet — fill in as you go

```
Group #: ______      Your role: __________________

Phase 3 — NORMAL_OPS
  One sensor whose normal range surprised me: __________

Phase 5 — DISCUSSION_1 (after ransomware)
  My instinct in the first 60 seconds:
    □ Pull cables       □ Wait and watch       □ Other: _______

  The biggest disagreement in our group was about: ______________

Phase 7 — DISCUSSION_2 (after the radio call)
  Pressure when we started talking: ______ bar
  Pressure when we voted:            ______ bar

  Did anyone change their mind during this phase?   Yes  /  No
  If yes, what changed it: _______________________

Phase 8 — ULTIMATUM
  My vote:                                        A   /   B
  Our group's vote:                               A   /   B  (tally __ / __)

Phase 9 — OUTCOME
  Result: ☐ Shutdown   ☐ Close call   ☐ Tank rupture

  One sentence about how I feel right now: _______________________

DEBRIEF — one thing I want to remember from this lab:
  _______________________________________________
```

---

## 10. Before you leave the room

- Your event log is saved on the server. The instructor can replay the
  exact sensor readings, votes, and timing for your group during the
  debrief. Decisions are auditable.
- The simulator is open-source. If you want to run it yourself or read the
  scenario engine code, ask the instructor for the repository link.
- This lab is part of a series. Lab 4 will move from *human* decision-making
  under attack to *automated* defence — specifically, how a data diode
  protects exactly this kind of plant from this kind of attack.

---

*Meridian Chemicals is a fictional company. The HAI 21.03 sensor data is
real, from the Korean ETRI testbed (Shin et al., 2020). The dilemma is
based on patterns observed across multiple real OT ransomware incidents
2017–2023.*
