---
name: research
description: Multi-agent research-to-LaTeX article pipeline with interactive intake, multi-model routing, reviewer loops, and cross-run quality heuristics.
version: 1.3.0
author: Hermes Agent + OpenClaw
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [Research, Writing, LaTeX, Telegram, Multi-Agent]
    related_skills: [arxiv, ml-paper-writing]
---

# Research Article Pipeline

Use this skill when the user wants a source-grounded, publication-ready LaTeX paper generated through a structured pipeline:

**research → writing (section by section) → multi-review → synthesis → revision → final LaTeX delivery**

Invoke via: `/research`

---

## What This Skill Must Do

1. Run an interactive intake — questions asked **one at a time**, in order.
2. Show a confirmation block including **model routing suggestions** based on the user's active provider.
3. Wait for explicit user confirmation before proceeding.
4. Launch the orchestration script.
5. Return a concise delivery summary of local artifacts only.

---

## Intake Flow

Ask questions **one at a time**, in this exact order. Wait for the answer before asking the next.

**Q1 — Topic**
"What topic do you want to research?"

**Q2 — Hypothesis**
"What is your central hypothesis or research question?"

**Q3 — Title**
"What should the title of the paper be? (Can be refined later)"

**Q4 — Field / Discipline**
"Which academic field is this for? (e.g. economics, sociology, computer science, engineering, psychology — or interdisciplinary)"

**Q5 — Target Audience**
"Who is the target audience? (e.g. academic researchers, policymakers, general educated public, practitioners)"

**Q6 — Tone**
"What tone do you want? (e.g. formal academic, accessible academic, technical, argumentative)"

**Q7 — Target Length**
"How long should the paper be?
- short (4,000–6,000 words)
- medium (8,000–12,000 words)
- long (12,000–18,000 words)"

**Q8 — Special Instructions** (optional)
"Any special instructions? (specific sources, arguments to emphasize, sections to add/skip, etc.) Reply 'none' to skip."

Do not start the pipeline until all 8 answers are collected.

---

## Confirmation Step

After collecting all answers, present this block:

```
Title:               <title>
Field:               <field>
Audience:            <audience>
Tone:                <tone>
Target length:       <length>
Research topics:     <comma-separated key themes>
Hypothesis:          <hypothesis, lightly reformulated>
Special instructions: <instructions or "none">
```

Then detect the user's active provider from `model_routing.yaml` and display model routing suggestions:

```
Suggested model routing (<provider>):
- Research agent:      <mid model>      — source discovery, brief compilation
- Writer agent:        <frontier model> — section-by-section drafting (heavyweight)
- Academic reviewer:   <mid model>      — structure and argument review
- General reviewer:    <cheap model>    — readability and engagement
- Source reviewer:     <mid model>      — citation verification
- Synthesizer:         <cheap model>    — merge reviewer feedback
- Quality gate:        <cheap model>    — pass/revise/warn decision

Paper written section by section to optimize token usage and depth.
```

If the provider is not in `model_routing.yaml`, list the models available to the user and ask them to assign frontier / mid / cheap tiers before continuing.

Ask: "Does this look correct? Confirm to proceed, or let me know what to change."

Only proceed after explicit confirmation.

---

## Execution Step

Once confirmed, run:

```bash
~/.hermes/hermes-agent/venv/bin/python ~/.hermes/skills/research/research/scripts/orchestrate_article.py run \
  --topic "<topic>" \
  --hypothesis "<hypothesis>" \
  --title "<title>" \
  --tone "<tone>" \
  --audience "<audience>" \
  --length "<length>"
```

Additional flags (only when user explicitly requests):
- `--max-iterations N`
- `--compile-pdf` — local PDF compilation on the VPS
- `--skip-github-push` — disable GitHub push for this run
- `--skip-overleaf-compile` — disable Overleaf sync
- `--skip-publishing-hub` — disable publishing hub update
- `--skip-netlify-deploy` — disable Netlify deploy

Always quote shell arguments safely.

**Default behavior: no automatic GitHub push, no Netlify deploy, no Overleaf sync unless the user has those configured and explicitly wants them.**

---

## After Script Completion

Read the script output carefully.

**If insufficient credible sources:**
- Tell the user the run was halted intentionally
- Report the warning plainly
- Do not pretend an article was produced

**If successful**, summarize:
- Run ID and run directory
- Final quality score
- Iteration count
- Manuscript word count / section count / subsection count
- Local paths: `article.tex`, `references.bib`, `review_summary.md`, `run_evaluation.md`
- `article.pdf` path if local compilation was requested and succeeded

Do **not** mention or promise GitHub, Netlify, or Overleaf URLs unless the user has those integrations configured and running.

End with:
> You can use `/reviewlast`, `/articlelast`, and `/feedback` to continue working on this paper.

---

## Companion Commands

- `/reviewlast` — show the latest review summary
- `/articlelast` — show the latest manuscript
- `/feedback <message>` — send feedback to improve the pipeline

Do not reimplement these inline.

---

## Supporting Files

Load when needed:
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

- Ask one question at a time — never bundle intake questions.
- Do not skip the confirmation step.
- Do not continue after a weak-source halt.
- Do not claim GitHub push, Netlify, or Overleaf will work — only mention them if the user has those integrations configured.
- Do not trigger GitHub-side LaTeX compilation.
- Always detect the provider from `model_routing.yaml`; never hardcode a provider assumption.
- If provider is unknown, ask the user to assign model tiers before running.

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
