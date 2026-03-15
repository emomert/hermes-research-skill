#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def load_user_env() -> None:
    env_path = Path.home() / '.hermes' / '.env'
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())


load_user_env()

HUB_DIR = Path.home() / 'hermes_article_pipeline' / 'publishing_hub'
SITE_DIRNAME = 'site'

STYLE = """
:root {
  --bg: #0b1020;
  --panel: #121933;
  --panel-2: #172042;
  --text: #eef2ff;
  --muted: #a7b0d6;
  --accent: #7dd3fc;
  --accent-2: #c084fc;
  --good: #34d399;
  --warn: #fbbf24;
  --bad: #f87171;
  --border: rgba(255,255,255,0.08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 0;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  background: linear-gradient(180deg, #0b1020 0%, #0f1630 100%);
  color: var(--text);
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
.container { max-width: 1180px; margin: 0 auto; padding: 32px 20px 64px; }
.hero {
  background: linear-gradient(135deg, rgba(125,211,252,0.12), rgba(192,132,252,0.12));
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 28px;
  margin-bottom: 24px;
}
.hero h1 { margin: 0 0 10px; font-size: 2.2rem; }
.hero p { margin: 8px 0; color: var(--muted); line-height: 1.55; }
.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px;
  margin: 20px 0 0;
}
.meta-card, .card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 16px 18px;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 18px;
}
.label { color: var(--muted); font-size: 0.9rem; margin-bottom: 6px; }
.value { font-size: 1.02rem; line-height: 1.45; }
.badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 0.88rem;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
}
.badge.good { color: var(--good); }
.badge.warn { color: var(--warn); }
.badge.bad { color: var(--bad); }
.paper-card {
  background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 18px;
}
.paper-card h3 { margin: 0 0 10px; font-size: 1.18rem; line-height: 1.35; }
.paper-card p { color: var(--muted); line-height: 1.55; }
.link-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}
.link-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 9px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  font-size: 0.92rem;
}
.section-title {
  margin: 28px 0 16px;
  font-size: 1.1rem;
  color: #dbe4ff;
}
pre, .mono {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.footer {
  color: var(--muted);
  margin-top: 40px;
  font-size: 0.92rem;
}
"""


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def read_text(path: Path, default: str = '') -> str:
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return default


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def html_escape(text: str) -> str:
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))


def strip_latex(text: str) -> str:
    text = re.sub(r'%.*', '', text)
    text = re.sub(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', r'\1', text, flags=re.S)
    text = re.sub(r'\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{([^{}]|\{[^{}]*\})*\})?', ' ', text)
    text = text.replace('{', ' ').replace('}', ' ')
    text = text.replace('\\', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_abstract(article_tex: str) -> str:
    m = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', article_tex, flags=re.S)
    if not m:
        return ''
    abstract = m.group(1)
    abstract = re.sub(r'\\citep\{[^}]*\}', '', abstract)
    abstract = re.sub(r'\\citet\{[^}]*\}', '', abstract)
    return strip_latex(abstract)


def preview(text: str, limit: int = 320) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + '…'


def badge_class(decision: str) -> str:
    decision = (decision or '').lower()
    if decision == 'pass':
        return 'good'
    if decision == 'warn' or decision == 'revise':
        return 'warn'
    return 'bad'


def render_layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>{html_escape(title)}</title>
  <style>{STYLE}</style>
</head>
<body>
  <div class='container'>
    {body}
  </div>
</body>
</html>
"""


def render_index(records: list[dict], repo_url: str, netlify_url: str | None) -> str:
    cards = []
    sorted_records = sorted(records, key=lambda x: x.get('updated_at', ''), reverse=True)
    for r in sorted_records:
        links = []
        if r.get('has_pdf'):
            links.append(f"<a class='link-btn' href='papers/{r['run_id']}/article.pdf'>PDF</a>")
        links.extend([
            f"<a class='link-btn' href='papers/{r['run_id']}/index.html'>Review page</a>",
            f"<a class='link-btn' href='papers/{r['run_id']}/article.tex'>article.tex</a>",
            f"<a class='link-btn' href='papers/{r['run_id']}/review_summary.md'>review summary</a>",
        ])
        if r.get('source_repo'):
            links.append(f"<a class='link-btn' href='{r['source_repo']}'>source repo</a>")
        cards.append(
            f"""
            <article class='paper-card'>
              <div class='badge {badge_class(r.get('decision',''))}'>Decision: {html_escape(r.get('decision','unknown'))}</div>
              <h3><a href='papers/{r['run_id']}/index.html'>{html_escape(r['title'])}</a></h3>
              <p>{html_escape(r.get('abstract_preview') or r.get('topic') or '')}</p>
              <div class='meta-grid'>
                <div class='meta-card'><div class='label'>Updated</div><div class='value'>{html_escape(r.get('updated_at',''))}</div></div>
                <div class='meta-card'><div class='label'>Quality</div><div class='value'>{html_escape(str(r.get('quality_score','')))}</div></div>
                <div class='meta-card'><div class='label'>Words</div><div class='value'>{html_escape(str(r.get('word_count','')))}</div></div>
                <div class='meta-card'><div class='label'>Citations</div><div class='value'>{html_escape(str(r.get('citation_count','')))}</div></div>
              </div>
              <div class='link-row'>{''.join(links)}</div>
            </article>
            """
        )
    netlify_line = f"<div class='meta-card'><div class='label'>Netlify</div><div class='value'><a href='{netlify_url}'>{netlify_url}</a></div></div>" if netlify_url else ''
    body = f"""
      <section class='hero'>
        <h1>Hermes Research Publishing Hub</h1>
        <p>Automatically updated archive for papers generated by the Hermes research skill. Built for fast review: source repo, LaTeX source, review notes, and PDF access in one place.</p>
        <div class='meta-grid'>
          <div class='meta-card'><div class='label'>GitHub hub repo</div><div class='value'><a href='{repo_url}'>{repo_url}</a></div></div>
          {netlify_line}
          <div class='meta-card'><div class='label'>Papers tracked</div><div class='value'>{len(records)}</div></div>
        </div>
      </section>
      <h2 class='section-title'>Papers</h2>
      <section class='card-grid'>
        {''.join(cards)}
      </section>
      <div class='footer'>Generated automatically by Hermes research workflow.</div>
    """
    return render_layout('Research Publishing Hub', body)


def render_paper_page(record: dict) -> str:
    links = []
    if record.get('has_pdf'):
        links.append("<a class='link-btn' href='article.pdf'>Download PDF</a>")
    links.extend([
        "<a class='link-btn' href='article.tex'>article.tex</a>",
        "<a class='link-btn' href='references.bib'>references.bib</a>",
        "<a class='link-btn' href='review_summary.md'>review summary</a>",
        "<a class='link-btn' href='README.md'>README</a>",
    ])
    if record.get('source_repo'):
        links.append(f"<a class='link-btn' href='{record['source_repo']}'>Source repo</a>")
    body = f"""
      <a href='../../index.html'>← Back to publishing hub</a>
      <section class='hero'>
        <div class='badge {badge_class(record.get('decision',''))}'>Decision: {html_escape(record.get('decision','unknown'))}</div>
        <h1>{html_escape(record['title'])}</h1>
        <p>{html_escape(record.get('topic',''))}</p>
        <div class='link-row'>{''.join(links)}</div>
      </section>
      <section class='card-grid'>
        <div class='card'><div class='label'>Run ID</div><div class='value mono'>{html_escape(record['run_id'])}</div></div>
        <div class='card'><div class='label'>Updated</div><div class='value'>{html_escape(record.get('updated_at',''))}</div></div>
        <div class='card'><div class='label'>Quality score</div><div class='value'>{html_escape(str(record.get('quality_score','')))}</div></div>
        <div class='card'><div class='label'>Words / citations</div><div class='value'>{html_escape(str(record.get('word_count','')))} words / {html_escape(str(record.get('citation_count','')))} citations</div></div>
      </section>
      <h2 class='section-title'>Abstract preview</h2>
      <section class='card'><div class='value'>{html_escape(record.get('abstract_preview') or 'No abstract preview available.')}</div></section>
      <h2 class='section-title'>Review summary preview</h2>
      <section class='card'><div class='value mono'>{html_escape(record.get('review_preview') or 'No review preview available.')}</div></section>
      <div class='footer'>This page is generated from the latest archived run artifacts.</div>
    """
    return render_layout(record['title'], body)


def resolve_netlify_site(preferred_name: str) -> str:
    token = os.getenv('NETLIFY_AUTH_TOKEN', '').strip()
    if not shutil.which('netlify') or not token:
        return ''
    listed = run(['netlify', 'sites:list', '--json', '--auth', token])
    if listed.returncode == 0:
        try:
            sites = json.loads(listed.stdout or '[]')
            for site in sites:
                if site.get('name') == preferred_name or site.get('id') == preferred_name or site.get('site_id') == preferred_name:
                    return site.get('id') or site.get('site_id') or ''
        except Exception:
            pass
    created = run(['netlify', 'sites:create', '--disable-linking', '--name', preferred_name, '--auth', token])
    if created.returncode == 0:
        listed = run(['netlify', 'sites:list', '--json', '--auth', token])
        if listed.returncode == 0:
            try:
                sites = json.loads(listed.stdout or '[]')
                for site in sites:
                    if site.get('name') == preferred_name:
                        return site.get('id') or site.get('site_id') or ''
            except Exception:
                pass
    return ''


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description='Update the research publishing hub and optionally deploy it to Netlify')
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--paper-github-url', default='')
    parser.add_argument('--owner', default=os.getenv('PUBLISHING_HUB_OWNER', 'emomert'))
    parser.add_argument('--repo', default=os.getenv('PUBLISHING_HUB_REPO', 'research-publishing-hub'))
    parser.add_argument('--hub-dir', default=str(HUB_DIR))
    parser.add_argument('--skip-netlify', action='store_true')
    parser.add_argument('--netlify-site', default=os.getenv('PUBLISHING_HUB_NETLIFY_SITE', '').strip())
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(json.dumps({'status': 'skipped', 'reason': f'run directory not found: {run_dir}'}))
        return 0
    if not shutil.which('gh'):
        print(json.dumps({'status': 'skipped', 'reason': 'gh CLI is required for publishing hub updates'}))
        return 0
    if run(['gh', 'auth', 'status']).returncode != 0:
        print(json.dumps({'status': 'skipped', 'reason': 'gh auth is not ready'}))
        return 0

    hub_dir = Path(args.hub_dir).expanduser().resolve()
    site_dir = hub_dir / SITE_DIRNAME
    records_path = site_dir / 'papers.json'
    owner_repo = f"{args.owner}/{args.repo}"
    repo_url = f"https://github.com/{owner_repo}"

    if not hub_dir.exists():
        hub_dir.mkdir(parents=True, exist_ok=True)
        if run(['gh', 'repo', 'view', owner_repo]).returncode != 0:
            create = run(['gh', 'repo', 'create', owner_repo, '--public'])
            if create.returncode != 0:
                print(json.dumps({'status': 'failed', 'reason': create.stderr or create.stdout or 'failed to create hub repo'}))
                return 0
        run(['git', 'init', '-b', 'main'], cwd=hub_dir)
        run(['git', 'remote', 'add', 'origin', f'https://github.com/{owner_repo}.git'], cwd=hub_dir)
    else:
        if not (hub_dir / '.git').exists():
            run(['git', 'init', '-b', 'main'], cwd=hub_dir)
        if run(['git', 'remote', 'get-url', 'origin'], cwd=hub_dir).returncode != 0:
            run(['git', 'remote', 'add', 'origin', f'https://github.com/{owner_repo}.git'], cwd=hub_dir)
    run(['git', 'config', 'user.name', 'Hermes Agent'], cwd=hub_dir)
    run(['git', 'config', 'user.email', 'hermes-agent@local'], cwd=hub_dir)

    request = read_json(run_dir / 'request.json', {})
    evaluation = read_json(run_dir / 'run_evaluation.md', {})
    latest = read_json(Path.home() / 'hermes_article_pipeline' / 'latest_run.json', {})
    article_tex = read_text(run_dir / 'article.tex')
    review_summary = read_text(run_dir / 'review_summary.md')
    run_id = request.get('run_id') or run_dir.name

    paper_dir = site_dir / 'papers' / run_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    for name in ['article.tex', 'references.bib', 'review_summary.md', 'README.md', 'request.json']:
        src = run_dir / name
        if src.exists():
            shutil.copy2(src, paper_dir / name)
    pdf_src = run_dir / 'article.pdf'
    has_pdf = False
    if pdf_src.exists():
        shutil.copy2(pdf_src, paper_dir / 'article.pdf')
        has_pdf = True

    metrics = evaluation.get('manuscript_checks', {}) if isinstance(evaluation, dict) else {}
    record = {
        'run_id': run_id,
        'title': request.get('title', run_id),
        'topic': request.get('topic', ''),
        'decision': latest.get('decision', evaluation.get('decision', '')),
        'quality_score': evaluation.get('average_score', ''),
        'updated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'source_repo': args.paper_github_url,
        'has_pdf': has_pdf,
        'abstract_preview': preview(extract_abstract(article_tex), 420),
        'review_preview': preview(review_summary, 500),
        'word_count': metrics.get('word_count', ''),
        'citation_count': metrics.get('citation_count', ''),
    }
    write(paper_dir / 'index.html', render_paper_page(record))

    records = read_json(records_path, [])
    records = [r for r in records if r.get('run_id') != run_id]
    records.append(record)
    write(records_path, json.dumps(records, indent=2, ensure_ascii=False) + '\n')

    netlify_url = ''
    write(site_dir / 'index.html', render_index(records, repo_url, None))

    run(['git', 'add', '.'], cwd=hub_dir)
    if run(['git', 'diff', '--cached', '--quiet'], cwd=hub_dir).returncode != 0:
        run(['git', 'commit', '-m', f'Update publishing hub for {run_id}'], cwd=hub_dir)
    run(['git', 'push', '-u', 'origin', 'main', '--force'], cwd=hub_dir)

    if not args.skip_netlify and shutil.which('netlify') and os.getenv('NETLIFY_AUTH_TOKEN'):
        token = os.getenv('NETLIFY_AUTH_TOKEN', '').strip()
        site_name = args.netlify_site or args.repo
        site_id = resolve_netlify_site(site_name)
        deploy_cmd = ['netlify', 'deploy', '--prod', '--dir', str(site_dir), '--json', '--auth', token]
        if site_id:
            deploy_cmd.extend(['--site', site_id])
        else:
            deploy_cmd.extend(['--create-site', site_name])
        deploy = run(deploy_cmd, cwd=hub_dir)
        if deploy.returncode == 0:
            try:
                deploy_info = json.loads(deploy.stdout or '{}')
                netlify_url = deploy_info.get('deploy_url') or deploy_info.get('url') or deploy_info.get('ssl_url') or ''
            except Exception:
                netlify_url = ''
        write(site_dir / 'index.html', render_index(records, repo_url, netlify_url or None))
        run(['git', 'add', str(site_dir / 'index.html')], cwd=hub_dir)
        if run(['git', 'diff', '--cached', '--quiet'], cwd=hub_dir).returncode != 0:
            run(['git', 'commit', '-m', f'Update netlify metadata for {run_id}'], cwd=hub_dir)
            run(['git', 'push', 'origin', 'main', '--force'], cwd=hub_dir)

    print(json.dumps({'status': 'ok', 'hub_repo_url': repo_url, 'netlify_url': netlify_url, 'paper_page': f'{repo_url}/tree/main/{SITE_DIRNAME}/papers/{run_id}'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
