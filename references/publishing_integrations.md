# Publishing Integrations: Overleaf + Publishing Hub + Netlify

This note documents the optional integrations now supported by the research skill.

## What is supported

1. Source repo push (existing behavior)
- Each paper run can still be pushed to its own GitHub repository.

2. Overleaf remote compilation via olcli
- The pipeline can sync the generated LaTeX into an existing Overleaf project.
- It can then trigger Overleaf's remote compiler and download `article.pdf` back into the run directory.
- This avoids compiling LaTeX on the VPS.

3. Publishing-hub repository
- The pipeline can maintain a separate GitHub repo that acts as an archive / website source for all generated papers.
- It stores one page per run plus an index page.

4. Netlify deployment
- If Netlify CLI and auth are configured, the publishing-hub static site can be deployed automatically.

## Recommended Overleaf workflow

The recommended workflow is to use one reusable Overleaf project, for example:
- `Hermes Auto Research`

The current `olcli` integration supports auth, pull/push/sync, and compile, and it assumes that this project already exists.

So the intended behavior is now:
- you create one Overleaf project manually once
- set `OVERLEAF_PROJECT_NAME="Hermes Auto Research"`
- for each new paper, Hermes overwrites the project files with the latest manuscript
- Hermes triggers Overleaf compilation remotely
- Hermes downloads the resulting PDF back into the run directory
- Hermes then pushes source artifacts / PDF to GitHub and updates the publishing hub / Netlify site

This is now the preferred workflow, because it keeps the Overleaf side simple and turns it into a reusable remote compile-and-review workspace.

## Authentication requirements

### Overleaf
Your Google-login Overleaf account is fine.
What Hermes needs on the VPS is the session cookie.

Set one of these environment variables on the VPS:
- `OVERLEAF_SESSION_COOKIE`
- or `OVERLEAF_SESSION2`

Also set:
- `OVERLEAF_PROJECT_NAME`

How to get the cookie:
1. Log into Overleaf in your browser.
2. Open browser dev tools.
3. Copy the `overleaf_session2` cookie value.
4. Put it on the VPS as an env var.

Example:
```bash
export OVERLEAF_PROJECT_NAME="Hermes Research Review"
export OVERLEAF_SESSION_COOKIE="..."
```

### GitHub
The existing GitHub push flow uses `gh auth` on the VPS.
So you need:
```bash
gh auth login
```
or an already authenticated `gh` session.

### Netlify
Your GitHub-backed Netlify account is also fine.
Hermes does not need SSH to Netlify; it needs auth available on the VPS.

Preferred setup:
- install Netlify CLI on the VPS
- provide `NETLIFY_AUTH_TOKEN`

Optional additional variables:
- `PUBLISHING_HUB_OWNER` (default: `emomert`)
- `PUBLISHING_HUB_REPO` (default: `research-publishing-hub`)

Example:
```bash
npm install -g netlify-cli
export NETLIFY_AUTH_TOKEN="..."
export PUBLISHING_HUB_OWNER="emomert"
export PUBLISHING_HUB_REPO="research-publishing-hub"
```

## Do you need SSH?

Not for the integrations themselves.

You only need a way to place credentials / env vars onto the VPS and optionally run one-time auth commands there.
In practice that usually means either:
- SSH into the VPS once and configure them there, or
- set them through your server management workflow.

So the answer is:
- SSH is not part of the runtime workflow
- but SSH is the simplest way to do one-time setup on the VPS

## New pipeline flags

The orchestrator now supports:
- `--skip-overleaf-compile`
- `--skip-publishing-hub`
- `--skip-netlify-deploy`

Local LaTeX compilation remains available via:
- `--compile-pdf`

## Default behavior

- If `--compile-pdf` is used, local VPS compilation is attempted.
- Otherwise, Hermes may attempt Overleaf compilation unless `--skip-overleaf-compile` is set.
- GitHub source repo push remains on by default unless `--skip-github-push` is used.
- Publishing-hub update is attempted by default unless `--skip-publishing-hub` is used.
- Netlify deploy is attempted only if Netlify CLI and auth are present, unless `--skip-netlify-deploy` is used.
