# Demo script: Shop Coach in Bay Log (about 5 minutes)

**The one-line idea:** *Judgment in the prompt, rules in code.* The model decides how to coach; plain code decides whether the answer is allowed to reach the student.

## Before you present
1. `./setup.sh reset` (fresh sample data) and `./setup.sh status`: Claude `ok`, local model `ok`.
2. Open the URL, open **Shop Coach**: the header should read **Claude · on-prem backup ready** (green dot).
3. Ask one question to warm up, then reload the page, close any ticket and leave the board showing.
4. Record a full rehearsal run tonight as the fallback.

## The run
**1. The app as it is (30 s).** "This is Bay Log, the repair-order system our automotive students use. Each vehicle moves through Intake → Diagnosis → Approval → Bay → QC."

**2. Open T-1001, the Honda Civic (30 s).** Point at code **P0303** and the yellow box: *Diagnostic findings is required.* "The student is stuck in Diagnosis."

**3. Ask the coach (about 10–20 s).** **Shop Coach** → **What should I check next?**
- Point at **→ Opened T-1001**: "It reads this exact ticket through the same API the screen uses. It doesn't guess."
- When it answers, read it aloud. Point out the shape: what the ticket shows, the next step *and why*, the shop's own procedure (**KB-1**), an everyday comparison, and a question at the end. "It coaches. It doesn't hand over the answer key."

**4. The checks (60 s). This is the slide-worthy moment.** Point at the green chips under the answer.
- "Before the student sees anything, plain code checks the answer: every ticket number, code and spec has to come from the records; it has to cite the procedure; no 'simply' or 'obviously'; it ends with one question; it can't claim it changed anything."
- If **↻ revised once** shows: "The first draft failed a check, so it was sent back and fixed before the student saw it." If not: "This one passed first time; when a draft fails, it gets one rewrite."
- "The AI provides the judgment and the code enforces the rules. That's the same architecture as Emile, our instructional-design assistant."

**5. Show it searching (30 s).** Close the ticket and ask **Find the work order for the F-150**. Point at **→ Searched tickets: F-150** and the safety line about instructor sign-off on brakes.

**6. The safety line (30 s).** Ask **"Advance T-1001 to the next stage."** It says it can't. "Read-only by design. People sign off on repairs; the AI helps them think."

**7. Close (30 s).** "Claude is the coaching voice. If the cloud drops, the shop's own server takes over automatically, and you saw a status line for that. Bay Log itself wasn't changed, and this demo uses sample data only. Real student records would stay on the on-prem model or wait for a data agreement."

## If something goes wrong
| Symptom | Say / do |
|---|---|
| "Switching to the on-prem model…" | Use it: "The internet just blinked, and the shop server took over. That's the backup working." Answers take 20–60 s on CPU. |
| A red ✗ chip on an answer | Good teaching moment: "The rules caught it, and it's flagged instead of hidden. This is why the rules live in code." |
| Header says `Claude: key rejected` | `./setup.sh key` again, or present on the local model: `./setup.sh key --remove`. |
| Page won't load | `./setup.sh status` in the container; `./setup.sh` again restarts everything. Otherwise use the recording. |
