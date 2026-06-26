# Lab 3 — The "Blind Operator" Incident Response Tabletop

> **About this manual.** Sections in plain prose are scaffold — concrete
> mechanics of running the lab. Sections in **`[INSTRUCTOR: …]`** brackets
> are placeholders. Fill them in with your voice, your stories, your
> opinions. Strike out anything you disagree with. Nothing here is sacred
> except the lab spec itself.

---

## Cover

| | |
|---|---|
| **Lab** | 3 of the OT Security series |
| **Format** | Group exercise, instructor-paced tabletop |
| **Duration** | 60 minutes (spec calls T+10 / T+20 / T+30 / debrief) |
| **Group size** | 4–5 students |
| **You will need** | A laptop or phone with a modern browser |

---

## 1. Why we run this lab

> **`[INSTRUCTOR: write 3–5 sentences in your own voice. Why this lab matters
> to you. Suggestions to react to — keep, replace, or ignore:`**
>
> - **`A real OT incident you want students to think about (e.g. Norsk Hydro
>   2019, Colonial Pipeline 2021, Triton/Trisis 2017, the 2024 Halliburton
>   ransomware), and one sentence on what was actually at stake.`**
> - **`A line about why you don't trust the standard IT incident-response
>   playbook for OT environments.`**
> - **`What you've seen go wrong when IT and OT teams disagree under
>   pressure — from your career or from public reports.`**
>
> **`Two-three sentences is enough. This sets the tone for the whole hour. ]`**

---

## 2. The scenario

The instructor will read this aloud:

> *Ransomware has locked the control screens. The physical chemical mixing
> machines are running, but you cannot see the pressure levels.*

That is the entire briefing. Everything else you will discover inside the
simulation.

> **`[INSTRUCTOR: optional — name the fictional plant. Default in the
> simulator is "Meridian Chemicals — Plant 4". Localise it if you want — to
> a real plant near campus, or to a process the students have studied
> elsewhere in the course. ]`**

---

## 3. Your role

The simulator will assign one of these four roles to each group member.
Read your role carefully — it shapes the entire hour for you.

### Plant Manager
You own the safety case. Only you can authorise a full emergency shutdown.
You — and only you — will see one pressure gauge below the ransomware lock
screen once the worker calls in. The buck stops with you.

### OT Engineer
You know the process and the PLCs. **When IT proposes pulling network
cables to contain the attack, you are the person who has to explain that
severing the network might also kill the automated safety valves.**

### IT/Cyber Lead
Your instinct is containment: isolate, eradicate, recover. You speak the
language of IT incident response — but this is not an IT environment. You
will collide with the OT Engineer in the first ten minutes. That is the
point.

### PR
You handle communications. The first questions you have to answer: do we
disclose? to whom? in what order? when? You are also the person who has to
imagine, out loud, the press release that follows each option.

### (Optional 5th role)
> **`[INSTRUCTOR: if your groups are 5 people instead of 4, name a 5th role
> and write 2–3 sentences on what they bring. Suggestions: Floor Supervisor
> (knows the workers personally), Insurer (cost focus), Plant Doctor /
> Safety Officer (regulatory exposure), or Board Member (reputation +
> career). Pick the angle that creates the most useful friction in your
> classroom. ]`**

**Coordinate so each role is filled exactly once per group.** If your
group is four, leave the 5th role unassigned.

---

## 4. Joining the simulation

1. Open the URL the instructor gives you.
2. Enter a display name, pick your group number, pick your role.
3. Click **Sign in**. You will see a waiting card while the rest of your
   group joins.
4. Top right of the screen always shows the current phase and your
   connection state. If it ever says "disconnected", refresh — your role
   is remembered.

---

## 5. How the hour unfolds

The instructor advances five beats. The simulator breaks each beat into
finer-grained phases internally, but the five beats are what you'll feel.

### Beat 1 — Briefing (T+0)
Quick read of the scenario above. Confirm roles. The simulator shows
**live sensor readings from a real industrial dataset** (HAI 21.03,
Korea ETRI). Use a minute to build a mental model of "what normal looks
like".

### Beat 2 — Inject 1: the ransomware (T+10)
The HMI is replaced by a ransomware lock screen. **The IT/Cyber Lead
will push for pulling network cables.** The OT Engineer needs to explain
why that may be worse than the attack itself. The rest of the group
arbitrates. The Plant Manager makes a call.

You have ~10 minutes here. Use it.

### Beat 3 — Inject 2: the worker on the radio (T+20)
A floor worker radios in: a physical pressure gauge by the tank is
climbing. The Plant Manager now sees one gauge through the lock screen.
The needle is moving.

The other roles cannot see the gauge. They must take the Plant Manager's
word for it. This is intentional.

### Beat 4 — The Ultimatum (T+30)
Five minutes to vote.

> **Option A — Emergency physical shutdown.**
> Destroys equipment. Loses millions. **Guarantees human safety.**
>
> **Option B — Keep it running blind.**
> Send a worker to manually vent the tank. Saves money and equipment.
> Risks explosion and life.

You vote independently. Strict majority wins. Ties broken by the
instructor.

### Beat 5 — Debrief
The Plant Manager from each group presents their decision and justifies
it to the room.

> **`[INSTRUCTOR: write the closing line in your own words. The spec says
> "physical safety always trumps system uptime." Write it the way you'd
> say it out loud to the room — short, blunt, memorable. This is the line
> students will remember six months later. ]`**

---

## 6. Things to weigh before you vote

> **`[INSTRUCTOR: this is the heart of the lab. Pick 1-3 considerations
> YOU think actually matter — not the textbook list. Some directions to
> react to:`**
>
> - **`The cost-of-life calculation. Production loss is concrete; safety
>   risk is probabilistic. Humans are bad at comparing those.`**
> - **`"It worked last time" is not safety. A near miss and a disaster
>   are the same event with a different random variable.`**
> - **`The attacker may still be in the system. The gauge value could
>   be spoofed. How would you tell?`**
> - **`Authority vs consensus. The Plant Manager can act unilaterally.
>   Why are we voting?`**
> - **`Something else — what you've actually seen groups miss when you've
>   run this or similar exercises.`**
>
> **`Write the version you believe. Strike out the rest. 3-5 sentences
> per point. ]`**

---

## 7. Debrief — Plant Manager presents

The Plant Manager from each group, in turn:

1. States the group's vote (A or B).
2. Names the one consideration that pushed them over.
3. Names the strongest argument they heard for the other side.

Then the instructor opens the room.

> **`[INSTRUCTOR: 2-3 questions YOU would actually ask. Suggestions to
> react to:`**
>
> - **`"Did anyone vote against their group? Why?"`**
> - **`"For groups that picked B — at what pressure reading would you have
>   switched to A?"`**
> - **`"Show of hands: who would change their vote now, knowing the
>   outcome?"`**
> - **`"If your group ran this again with the same roles, what would the
>   first five minutes of Inject 1 look different?"`**
>
> **`Pick the ones that matter to you. Add your own. ]`**

---

## 8. Glossary

- **OT** — Operational Technology. Computers that control physical things
  (valves, motors, reactors). Opposite of IT.
- **HMI** — Human-Machine Interface. The dashboard the operator stares at.
- **PLC** — Programmable Logic Controller. The small ruggedised industrial
  computer that drives the valves. The HMI talks to it. In this lab the
  PLC is unaffected by the ransomware — only the HMI is encrypted.
- **Ransomware** — malware that encrypts files and demands payment.
- **Cyber-physical system** — any system where a cyber attack can cause
  physical consequences. This reactor is one.

---

## 9. Record sheet

```
Group #: ______      Your role: __________________

Beat 2 — Inject 1
  Who pushed hardest for pulling cables? ____________
  Who pushed hardest against?            ____________
  What ended the argument?               ____________

Beat 3 — Inject 2 (worker radio)
  Pressure (per Plant Manager) when radio came in: ____ bar
  Pressure when vote opened:                       ____ bar

Beat 4 — Vote
  My vote:                A   /   B
  Our group's vote:       A   /   B    Tally: A=__  B=__

Beat 5 — Outcome
  Result: ___________________________________________

One thing I want to remember:
  __________________________________________________
```

---

## 10. After the lab

> **`[INSTRUCTOR: a pointer to what comes next. Optional. A reading you
> assign, what Lab 4 will cover, whether you want a written reflection. ]`**

---

> **Footer (you can delete this).** The HAI 21.03 sensor data is real
> (Korea ETRI). The chemical plant and the ransomware demand are
> fictional. The dilemma is the lab spec's, written by [INSTRUCTOR: course
> coordinator's name].
