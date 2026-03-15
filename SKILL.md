---
name: research
description: Multi-agent research-to-LaTeX article pipeline with Telegram intake, reviewer loops, and cross-run quality heuristics.
version: 1.1.0
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
research -> writing -> multi-review -> synthesis -> revision -> final LaTeX delivery.

This skill is designed for Telegram use and should be invoked via:
/research

## What This Skill Must Do

1. Run a 3-question intake before any research starts.
2. Show a confirmation block and wait for explicit user confirmation.
3. Launch the orchestration script that performs the full pipeline.
4. Return a concise delivery summary focused on the generated local artifacts, manuscript-depth metrics, and point the user to /reviewlast, /articlelast, and /feedback.

## Intake Flow

If the user has not already provided all three fields, ask exactly these three questions in one message:

1. What topic do you want to research?
2. What is your hypothesis or central research question?
3. What should the title of the paper be?

Do not start the pipeline until you have all three answers.

## Confirmation Step

After receiving the answers, generate a short derived research-topics line and print this exact structure:

Title of the paper: <title>
Research topics: <comma-separated key themes and subtopics you will investigate>
Hypothesis question: <hypothesis, lightly reformulated if needed for clarity>

Then ask the user to confirm or correct it.
Only proceed after explicit confirmation.

## Execution Step

Once the user confirms, run this command with terminal:

~/.hermes/hermes-agent/venv/bin/python ~/.hermes/skills/research/research/scripts/orchestrate_article.py run \
  --topic "<topic>" \
  --hypothesis "<hypothesis>" \
  --title "<title>"

Optional fields you may append when the user specifies them:
- --tone "..."
- --audience "..."
- --length "..."
- --max-iterations N
- --compile-pdf  (only if the user explicitly wants local compilation on the current machine)
- --skip-overleaf-compile  (only if the user explicitly does not want remote Overleaf compilation when configured)
- --skip-github-push  (only if the user explicitly does not want GitHub publishing for that run)
- --skip-publishing-hub  (only if the user explicitly does not want the publishing-hub repo/site updated)
- --skip-netlify-deploy  (only if the user wants the hub repo updated without pushing a new Netlify deploy)

Always quote shell arguments safely.

## After Script Completion

Read the script output carefully.

If the script reports insufficient credible sources:
- tell the user the run was halted intentionally
- report the warning plainly
- do not pretend an article was produced

If the script succeeds:
- summarize the final result in a compact terminal-friendly format
- include:
  - run id / run directory
  - final quality score
  - iteration count
  - manuscript word count / section count / subsection count
  - local paths for article.tex and review_summary.md
  - article.pdf path if local or Overleaf compilation produced one
  - GitHub source repo URL if created
  - publishing-hub / Netlify URLs if configured and updated
- prefer delivering the final local LaTeX output and related artifact paths first
- GitHub push of the final source artifacts is the default expected behavior
- when configured, the pipeline may also:
  - sync the latest manuscript into an existing Overleaf project via olcli and download a remotely compiled PDF
  - update a separate publishing-hub GitHub repo and deploy its static site with Netlify CLI
- do not require or emphasize local VPS compilation or repository-side LaTeX builds
- a short paper should not be framed as publication-ready if the manuscript-depth checks indicate otherwise
- end with a short note that the user can use:
  - /reviewlast
  - /articlelast
  - /feedback <message>

## Companion Commands

This skill works with three companion skills installed separately:
- /reviewlast
- /articlelast
- /feedback

Do not reimplement those behaviors inline if the user explicitly invokes those commands; let the companion skills handle them.

## Supporting Files To Load If Needed

This skill includes supporting files you can inspect with skill_view when needed:
- templates/research_prompt.md
- templates/writer_prompt.md
- templates/reviewer_academic.md
- templates/reviewer_general.md
- templates/reviewer_source.md
- templates/synthesizer_prompt.md
- templates/quality_gate_prompt.md
- references/architecture.md
- references/editorial_heuristics.md
- references/feedback_schema.md
- references/model_routing.md
- references/telegram_commands.md
- references/publishing_integrations.md
- model_routing.yaml
- scripts/orchestrate_article.py
- scripts/overleaf_compile.py
- scripts/publish_hub.py

Note: the desired default outcome of this skill is final local LaTeX source delivery plus a GitHub push of those source artifacts. Local VPS PDF compilation remains non-essential and should stay disabled unless explicitly requested.

## Pitfalls

- Do not skip the confirmation step.
- Do not continue after a weak-source halt.
- Do not trigger or encourage GitHub-side LaTeX compilation just to produce a final answer.
- Do not claim Telegram native slash-menu registration exists; dynamic skills work through Hermes command routing and may require gateway restart to appear in help/cache.
- Do not promise /feedback or /reviewlast are built-in platform commands; they are companion skills.

## Verification

A successful run should leave artifacts under:
~/hermes_article_pipeline/runs/<run-id>/

Minimum expected outputs:
- article.tex
- references.bib
- research_brief.md
- review_summary.md
- README.md
- run_evaluation.md
