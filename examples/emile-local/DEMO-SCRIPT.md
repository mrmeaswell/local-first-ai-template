# Demo script: Emile, local (about 6 minutes)

**The one-line idea:** *Judgment in the prompt, rules in code.* The model decides how to teach; plain code decides what's allowed in and what's allowed out.

**The analogy:** Emile's repo is a music library plus a tuner. Any musician can play the sheet music: Claude in the cloud, or a smaller model on our own server. The tuner checks every note, and it doesn't care who played.

## Before you present
1. `./setup.sh status`: `emile ok`, `claude ok`, `ollama ok`.
2. Open the page. The header should read **Claude · on-prem backup ready** with a green dot.
3. Run one starter to warm things up, then reload the page so the screen is clean.
4. Record a rehearsal run tonight as the fallback.

## The run
**1. What it is (30 s).** "Emile is the curriculum collaborator I built on Pocket Pedagogy: adult learners, bridges from what they already know, shame-free, why before how. Before, it lived as a prompt and a set of rules. This is Emile with a screen, running on our own server."

**2. The three gates (30 s).** Point at *At the door / In the draft / On the way out*. "The AI is only the middle step. Both ends are plain code."

**3. Write a module intro (90 s).** Pick **CNT 290** in the course menu (the starters switch to worked CNT examples), then click **Write a module intro**. It fills the box. Change something out loud before sending, e.g. add "Add a bridge for learners coming from nursing," then press **Send**. "Nothing here is pre-recorded. You just watched me change the request."
- Point at the lookups: **Read course context: CNT 290**, **Read the MSCB story bible**. "It reads my course and our scenario before it writes. It isn't guessing."
- Read the Hook aloud: the bridge from a familiar job to the technical idea. Point at a highlighted term: "Every new term is marked. Code counts them, and more than five in a section fails."
- Point at the chips. If **↻ revised once** shows: "The first draft broke a rule. Code caught it and sent it back before I ever saw it."

**4. Quiz items (60 s).** Click **Draft sample quiz items**, then **Send**. Point at the cards: type, level, and a CompTIA objective on every item, with the right answers marked. "The quiz check is Emile's own validator: every item mapped to an objective, no 'all of the above', no double negatives, no trick items. The same code checks a full 35-item package before export to Canvas."

**5. Pushback (60 s).** Click **Review my draft**, then **Send**. "I wrote this badly on purpose." Emile names the deficit framing and gives a rewrite. "It's not a yes-machine. Pushing back is in its job description."

**6. The door (45 s). This is the moment to land.** Click **Help with a struggling student**, then **Send**. It's stopped: *Stopped at the door … Nothing was sent to any model.* "That check runs before the AI. A student's name, email, ID or grade never leaves the building, no matter which model is answering. That's FERPA enforced in code, not left to a prompt."

**6b. Audience's choice (60 s, if time).** "Someone name a concept you teach." Type it in and send. A request nobody could have prepared is the best proof it's live.

**7. Swap the musician (45 s, optional).** Tick **On-prem only** and ask something short, like "Give me a one-paragraph bridge for VLANs for a learner coming from retail." "Same Emile, same rules, now running entirely on our own hardware. Slower, because it's CPU only, but nothing leaves the building." While it works, point at the header status.

**7b. Any subject (30 s).** Switch the menu back to **Any subject**: the starters become fill-in templates. "For colleagues there's a link that hides my courses entirely. Pick a template, Tab through the brackets, and it works for nursing, welding, or accounting just as well."

**8. Close (30 s).** "The AI provides the judgment and the code enforces the rules. The model can change; the rules don't. And a person still publishes."

## If something goes wrong
| Symptom | Say / do |
|---|---|
| "Switching to the on-prem model…" | "The internet just blinked, and our own server took over. That's the backup working." Answers take one to a few minutes on CPU. |
| A red ✗ chip | "The rules caught it, and it's flagged instead of hidden." Hover the chip to read why. |
| Header says `Claude: key rejected` | `./setup.sh key` again, or present on-prem only. |
| Page won't load | `./setup.sh status`, then `./setup.sh` again. Otherwise use the recording. |
