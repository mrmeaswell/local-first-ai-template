# Demo script: Shop Helper in Bay Log (about 5 minutes)

## Before you present
1. `./setup.sh reset` (fresh sample data) and `./setup.sh status` (all green).
2. Open the URL, open **Shop Helper** once and ask anything. The first answer loads the model; get it out of the way before the audience arrives.
3. Close the helper, close any open ticket, and leave the board showing.
4. Have a fallback ready: a screen recording of a full rehearsal run (record it tonight).

## The run
**1. The app as it is (30 s).** "This is Bay Log, the repair-order system our automotive students use. Three vehicles, each moving through Intake → Diagnosis → Approval → Bay → QC."

**2. Open T-1001, the Honda Civic (30 s).** Point at the detail panel: code **P0303**, and the yellow box: *Diagnostic findings is required.* "The student is stuck in Diagnosis."

**3. Ask the helper (60–90 s on CPU).** Tap **Shop Helper** → **What should I check next?**
- While it works, point at the live line **→ Opened T-1001**. "It isn't guessing. It's reading this exact ticket through the same API the screen uses."
- Use the wait: "There's no GPU and no cloud here. This is a 7-billion-parameter model running on the shop server's CPU. Student data never leaves the building."
- When it answers: point at the code it repeated, the **KB-1** pill (the shop's own misfire procedure), and the question at the end. "It coaches. It doesn't hand over the answer."

**4. Show it searching (60 s).** Close the ticket, then ask **Find the work order for the F-150**. Point at **→ Searched tickets: F-150**. "When you describe a vehicle, it searches. It's tested so it never makes up a ticket number."

**5. The safety line (30 s).** Ask **"Advance T-1001 to the next stage."** It should say it can't. "Read-only by design. People sign off on repairs; the AI helps them think."

**6. Close (30 s).** "Bay Log itself wasn't changed. The helper sits in front of it, and every behavior you saw is covered by automated tests that run against the real model."

## If something goes wrong
| Symptom | Say / do |
|---|---|
| Answer takes over 2 minutes | "CPU only, no GPU." Keep narrating the lookup lines. If it stalls, switch to the recording. |
| Red dot / "Model offline" | `systemctl restart ollama shop-helper` in the container, or switch to the recording. |
| Odd or wrong answer | Good teaching moment: "This is why the tests exist, and why it's read-only." |
| Page won't load | `./setup.sh status` in the container; `./setup.sh` again restarts everything. |
