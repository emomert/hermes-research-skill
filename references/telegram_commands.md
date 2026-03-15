Telegram command behavior in this install:

- Hermes scans ~/.hermes/skills/**/SKILL.md and exposes each skill as /<normalized-name>
- These commands are handled by Hermes gateway routing, not by Telegram-native dynamic command registration
- Telegram's command picker will not automatically list newly created skills unless Hermes code is patched to do that
- A gateway restart may be required for a long-running process to refresh the in-memory skill command cache

Installed commands for this pipeline:
- /research
- /feedback
- /reviewlast
- /articlelast

Behavior note:
- /research is source-artifact-first by default: it delivers article.tex and related local files
- it does not compile a PDF locally unless the workflow explicitly uses --compile-pdf
- it does push the final source artifacts to GitHub by default
- that GitHub push can be disabled only when the workflow explicitly uses --skip-github-push
