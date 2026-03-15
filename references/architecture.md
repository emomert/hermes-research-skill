Architecture adapted to the current Hermes install:

- Entry command: /research (dynamic skill command loaded from ~/.hermes/skills)
- Companion commands: /feedback, /reviewlast, /articlelast
- Telegram invocation works through Hermes skill command routing, not Telegram's native dynamic slash menu
- Active runtime path uses helper script + Python AIAgent library calls
- Reviewer parallelism is handled inside the orchestration script with fresh AIAgent instances per reviewer
- Because current delegate_task is usable but not fully production-hardened for Telegram UX, this implementation chooses direct scripted orchestration for v1
- Run artifacts live under ~/hermes_article_pipeline/runs/<run-id>/
- Default deliverables are local source artifacts first: article.tex, references.bib, review_summary.md, README.md, and run_evaluation.md
- Local PDF compilation is disabled by default to reduce VPS load; enable it only with --compile-pdf when explicitly requested
- GitHub publishing is enabled by default for final source artifacts; disable it only with --skip-github-push when explicitly requested
- Cross-run data lives under ~/hermes_article_pipeline/
