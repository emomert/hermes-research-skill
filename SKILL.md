---
name: research
description: Multi-agent research-to-LaTeX article pipeline with Telegram intake, reviewer loops, and cross-run quality heuristics.
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Research, Writing, LaTeX, Telegram, Multi-Agent]
    related_skills: [arxiv, ml-paper-writing]
---

# Research Article Pipeline

Use this skill when the user wants a source-grounded, publication-ready paper or manuscript draft generated through a structured pipeline:
research -> writing (section by section) -> multi-review -> synthesis -> revision -> final LaTeX delivery.

This skill is designed for Telegram use and should be invoked via:
/research

## What This Skill Must Do

1. Run a structured intake (questions asked ONE AT A TIME, in order).
2. Show a confirmation block including model routing suggestions.
3. Wait for explicit user confirmation before proceeding.
4. Launch the orchestration script.
5. Return a concise delivery summary.

---

## Intake Flow

Ask questions ONE AT A TIME, in this exact order. Do not bundle questions. Wait for the answer before asking the next one.

**Step 1 — Topic**
Ask: "What topic do you want to research?"

**Step 2 — Hypothesis**
Ask: "What is your central hypothesis or research question?"

**Step 3 — Title**
Ask: "What should the title of the paper be? (You can refine it later)"

**Step 4 — Field / Discipline**
Ask: "Which academic field or discipline is this for? (e.g. economics, sociology, computer science, engineering, psychology — or interdisciplinary)"

**Step 5 — Target Audience**
Ask: "Who is the target audience? (e.g. academic researchers, policymakers, general educated public, practitioners)"

**Step 6 — Tone**
Ask: "What tone do you want? (e.g. formal academic, accessible academic, technical, argumentative)"

**Step 7 — Target Length**
Ask: "How long should the paper be? Options:
- short (4,000–6,000 words)
- medium (8,000–12,000 words)
- long (12,000–18,000 words)"

**Step 8 — Special Instructions** (optional)
Ask: "Any special instructions? For example: specific sources to include, specific arguments to emphasize, sections to add or skip, or anything else. (Reply 'none' to skip)"

Do not start the pipeline until all 8 answers are collected.

---

## Confirmation Step

After collecting all answers, generate a short derived research-topics line and present this exact block:

```
Title: <title>
Field: <field>
Audience: <audience>
Tone: <tone>
Target length: <length>
Research topics: <comma-separated key themes and subtopics>
Hypothesis: <hypothesis, lightly reformulated if needed>
Special instructions: <instructions or "none">
```

Then suggest model routing based on the user's current Hermes provider (read `~/.hermes/config.yaml` to detect it, then look up the corresponding tier mapping in `model_routing.yaml`):

```
Suggested model routing for your provider (<provider>):
- Research agent:      <mid-tier model>   — source discovery, brief compilation
- Writer agent:        <frontier model>   — section-by-section drafting (heavyweight)
- Academic reviewer:   <mid-tier model>   — structure and argument review
- General reviewer:    <cheap model>      — readability and engagement
- Source reviewer:     <mid-tier model>   — citation verification
- Synthesizer:         <cheap model>      — merge reviewer feedback
- Quality gate:        <cheap model>      — pass/revise/warn decision

Estimated token usage: moderate (paper written section by section to optimize depth)
```

Then ask: "Does this look correct? Confirm to proceed, or let me know what to change."

Only proceed after explicit confirmation.

---

## Execution Step

Once the user confirms, run this command:

```bash
~/.hermes/hermes-agent/venv/bin/python ~/.hermes/skills/research/research/scripts/orchestrate_article.py run \
  --topic "<topic>" \
  --hypothesis "<hypothesis>" \
  --title "<title>" \
  --tone "<tone>" \
  --audience "<audience>" \
  --length "<length>"
```

Additional flags:
- `--max-iterations N` — override default max iterations
- `--compile-pdf` — only if user explicitly wants local PDF compilation
- `--skip-overleaf-compile` — skip Overleaf sync for this run
- `--skip-github-push` — skip GitHub push for this run
- `--skip-publishing-hub` — skip publishing hub update
- `--skip-netlify-deploy` — skip Netlify deploy

Always quote shell arguments safely.

---

## After Script Completion

Read the script output carefully.

If the script reports insufficient credible sources:
- Tell the user the run was halted intentionally
- Report the warning plainly
- Do not pretend an article was produced

If the script succeeds, summarize in a compact format:
- Run ID and run directory
- Final quality score
- Iteration count
- Manuscript word count / section count / subsection count
- Local paths for article.tex and review_summary.md
- article.pdf path if produced
- GitHub source repo URL if created
- Publishing-hub / Netlify URLs if updated

End with:
> You can use /reviewlast, /articlelast, and /feedback to continue working on this paper.

---

## Companion Commands

This skill works with three companion skills:
- `/reviewlast` — show the latest review summary
- `/articlelast` — show the latest manuscript
- `/feedback <message>` — send feedback to improve the pipeline

Do not reimplement those behaviors inline.

---

## Supporting Files

Load these when needed:
- `templates/research_prompt.md`
- `templates/writer_prompt.md`
- `templates/reviewer_academic.md`
- `templates/reviewer_general.md`
- `templates/reviewer_source.md`
- `templates/synthesizer_prompt.md`
- `templates/quality_gate_prompt.md`
- `references/architecture.md`
- `references/editorial_heuristics.md`
- `references/feedback_schema.md`
- `references/model_routing.md`
- `references/telegram_commands.md`
- `references/publishing_integrations.md`
- `model_routing.yaml`
- `scripts/orchestrate_article.py`
- `scripts/overleaf_compile.py`
- `scripts/publish_hub.py`

---

## Pitfalls

- Do not ask multiple questions at once — one at a time, in order.
- Do not skip the confirmation step.
- Do not continue after a weak-source halt.
- Do not trigger GitHub-side LaTeX compilation.
- Do not claim Telegram native slash-menu registration exists.
- Do not promise /feedback or /reviewlast are built-in platform commands — they are companion skills.
- Always detect the provider from `~/.hermes/config.yaml` before suggesting models; never hardcode a provider.

---

## Verification

A successful run leaves artifacts under:
`~/hermes_article_pipeline/runs/<run-id>/`

Minimum expected outputs:
- `article.tex`
- `references.bib`
- `research_brief.md`
- `review_summary.md`
- `README.md`
- `run_evaluation.md`
