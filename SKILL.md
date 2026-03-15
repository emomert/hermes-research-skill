---
name: research
description: Multi-agent research-to-LaTeX article pipeline. Interactive intake, multi-model subagent orchestration, reviewer loops, quality gate, and final LaTeX delivery. Fully OpenClaw-native — no external scripts needed.
version: 2.0.0
author: OpenClaw
license: MIT
platforms: [linux]
---

# Research Article Pipeline

Orchestrate a full research-to-LaTeX pipeline using OpenClaw subagents.

Pipeline: **intake → research → write (section by section) → 3 reviewers (parallel) → synthesize → revise → quality gate → deliver**

Invoke via: `/research`

---

## Intake Flow

Ask questions ONE AT A TIME, in order. Wait for each answer before asking the next.

1. "What topic do you want to research?"
2. "What is your central hypothesis or research question?"
3. "What should the title of the paper be? (Can be refined later)"
4. "Which academic field is this for? (e.g. economics, sociology, CS, engineering, psychology)"
5. "Who is the target audience? (e.g. academic researchers, policymakers, practitioners)"
6. "What tone? (e.g. formal academic, accessible academic, technical, argumentative)"
7. "How long? — short (4–6k words) / medium (8–12k words) / long (12–18k words)"
8. "Any special instructions? (sources to include, arguments to emphasize, sections to skip, etc.) Reply 'none' to skip."

Do not proceed until all 8 answers are collected.

---

## Confirmation Step

Present the summary block:

```
Title:                <title>
Field:                <field>
Audience:             <audience>
Tone:                 <tone>
Target length:        <length>
Research topics:      <comma-separated key themes>
Hypothesis:           <hypothesis>
Special instructions: <instructions or "none">
```

Then show model routing (use the default model for all roles — the same model running this session):

```
Model routing (all roles use current session model):
- Research agent:    <current model>
- Writer agent:      <current model>
- Reviewer agents:   <current model> (×3, run in parallel)
- Synthesizer:       <current model>
- Quality gate:      <current model>
```

Ask: "Confirm to proceed, or let me know what to change."

Only proceed after explicit confirmation.

---

## Execution

### Step 1 — Research Agent

Spawn a subagent to produce a structured research brief.

```
sessions_spawn(
  task: "<Load the research prompt from the skill's templates/research_prompt.md, then research the topic below and return valid JSON as specified in that prompt.

Topic: <topic>
Hypothesis: <hypothesis>
Title: <title>
Field: <field>
Audience: <audience>
Tone: <tone>
Length: <length>
Special instructions: <instructions>

Target: 30-40 sources minimum, at least 15 peer-reviewed. Return ONLY valid JSON per the schema in research_prompt.md.>",
  runtime: "subagent"
)
```

Read `templates/research_prompt.md` and pass its full contents as the system prompt to the subagent.

If the subagent reports `status: insufficient_sources`:
- Tell the user the run was halted: insufficient credible sources found
- Do not proceed

Otherwise: extract `sources`, `research_brief_markdown`, `suggested_figures`, `suggested_outline` from the JSON output.

Create the run directory: `~/hermes_article_pipeline/runs/<YYYYMMDD_HHMMSS>/`
Save `research_brief.md` there.

---

### Step 2 — Writer Agent (section by section)

Read `templates/writer_prompt.md`. Spawn a writer subagent for each major section separately to optimize depth and token usage.

Sections (adapt based on field):
1. Introduction
2. Conceptual Framework / Literature Review
3. Data and Sources
4. Methodology
5. Results / Analysis
6. Discussion and Implications
7. Conclusion
8. References (BibTeX)

For each section, spawn:
```
sessions_spawn(
  task: "<You are the Writer Agent. Using the research brief and sources below, write ONLY the section: <section name>.

Research brief: <research_brief_markdown>
Sources (BibTeX): <bibtex_entries>
Prior sections written: <accumulated sections so far>
Title: <title>, Field: <field>, Tone: <tone>, Audience: <audience>
Special instructions: <instructions>

Follow all instructions in the writer prompt system message exactly. Return the LaTeX content for this section only.>",
  runtime: "subagent"
)
```

Accumulate sections. After all sections, assemble the full `article.tex` with proper `\documentclass`, packages, and `\end{document}`.

Save `article.tex` and `references.bib` to the run directory.

---

### Step 3 — Reviewers (spawn in parallel)

Spawn 3 reviewer subagents simultaneously using the templates:

- **Academic reviewer** (`templates/reviewer_academic.md`) — structure, argument, academic rigor
- **General reviewer** (`templates/reviewer_general.md`) — readability, engagement, clarity
- **Source reviewer** (`templates/reviewer_source.md`) — citation quality, source verification

Each receives the full `article.tex` and `research_brief_markdown`.

Each returns structured feedback JSON per the schema in `references/feedback_schema.md`.

---

### Step 4 — Synthesizer

Spawn a synthesizer subagent using `templates/synthesizer_prompt.md`.

Input: all 3 reviewer outputs.

Returns: a unified revision brief with:
- `must_fix` items (blocking)
- `should_fix` items (recommended)
- `optional` items

Save `review_summary.md` to run directory.

---

### Step 5 — Revision

Spawn a writer subagent again with the revision brief. Rewrite sections that have `must_fix` issues. Apply `should_fix` items where possible.

Save the revised `article.tex` (overwrite).

---

### Step 6 — Quality Gate

Spawn a quality gate subagent using `templates/quality_gate_prompt.md`.

Input: revised `article.tex` + `review_summary.md`.

Returns one of:
- `pass` — deliver to user
- `revise` — one more revision loop (max 2 total loops)
- `warn` — deliver with warnings

---

### Step 7 — Deliver

Save final artifacts to run directory:
- `article.tex`
- `references.bib`
- `research_brief.md`
- `review_summary.md`
- `run_evaluation.md` (quality score, iteration count, word count)
- `README.md`

Report to user:
```
Run ID:        <run-id>
Quality score: <score>
Iterations:    <n>
Word count:    ~<n> words
Sections:      <n>

Artifacts saved to: ~/hermes_article_pipeline/runs/<run-id>/
  - article.tex
  - references.bib
  - review_summary.md
  - run_evaluation.md
```

End with:
> Use `/reviewlast`, `/articlelast`, or `/feedback <message>` to continue.

---

## Supporting Templates

Always load these before spawning the relevant subagent:
- `templates/research_prompt.md` → research agent system prompt
- `templates/writer_prompt.md` → writer agent system prompt
- `templates/reviewer_academic.md` → academic reviewer system prompt
- `templates/reviewer_general.md` → general reviewer system prompt
- `templates/reviewer_source.md` → source reviewer system prompt
- `templates/synthesizer_prompt.md` → synthesizer system prompt
- `templates/quality_gate_prompt.md` → quality gate system prompt
- `references/feedback_schema.md` → reviewer output schema
- `references/editorial_heuristics.md` → cross-run quality heuristics

---

## Pitfalls

- Ask intake questions one at a time — never bundle them.
- Do not skip the confirmation step.
- Do not proceed past research if `status: insufficient_sources`.
- Write sections one by one — do not try to write the full paper in one subagent call.
- Do not invent BibTeX keys — only use keys from the research agent output.
- Max 2 revision loops total.
- Always load the template file before spawning each subagent — pass its content as the system prompt.
