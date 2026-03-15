#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
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

OVERLEAF_SYNC_DIR = Path.home() / '.cache' / 'hermes-overleaf-sync'
FILES_TO_SYNC = [
    'article.tex',
    'references.bib',
]
OPTIONAL_GLOBS = ['*.sty', '*.cls', '*.bst', '*.png', '*.jpg', '*.jpeg', '*.pdf', '*.svg', '*.eps']


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description='Sync a run to Overleaf and compile remotely with olcli')
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--project', default=os.getenv('OVERLEAF_PROJECT_NAME', '').strip())
    parser.add_argument('--cookie', default=os.getenv('OVERLEAF_SESSION_COOKIE', '').strip() or os.getenv('OVERLEAF_SESSION2', '').strip())
    parser.add_argument('--sync-dir', default=str(OVERLEAF_SYNC_DIR))
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    sync_dir = Path(args.sync_dir).expanduser().resolve()

    if not run_dir.exists():
        print(json.dumps({'status': 'skipped', 'reason': f'run directory not found: {run_dir}', 'pdf_path': '', 'log_path': '', 'command_statuses': []}, indent=2))
        return 0
    if not args.project:
        print(json.dumps({'status': 'skipped', 'reason': 'OVERLEAF_PROJECT_NAME not configured', 'pdf_path': '', 'log_path': '', 'command_statuses': []}, indent=2))
        return 0
    if not args.cookie:
        print(json.dumps({'status': 'skipped', 'reason': 'OVERLEAF_SESSION_COOKIE (or OVERLEAF_SESSION2) not configured', 'pdf_path': '', 'log_path': '', 'command_statuses': []}, indent=2))
        return 0
    if not shutil.which('npm'):
        print(json.dumps({'status': 'skipped', 'reason': 'npm is required for npx @aloth/olcli', 'pdf_path': '', 'log_path': '', 'command_statuses': []}, indent=2))
        return 0

    sync_dir.mkdir(parents=True, exist_ok=True)
    statuses: list[dict] = []
    logs: list[str] = []

    def record(name: str, proc: subprocess.CompletedProcess[str]) -> None:
        statuses.append({'command': name, 'returncode': proc.returncode})
        logs.append(f'$ {name}\n{proc.stdout}\n{proc.stderr}')

    auth = run(['npx', '-y', '@aloth/olcli', 'auth', '--cookie', args.cookie])
    record('npx -y @aloth/olcli auth --cookie ***', auth)
    if auth.returncode != 0:
        log_path = run_dir / 'overleaf_build.log'
        log_path.write_text('\n\n'.join(logs), encoding='utf-8')
        print(json.dumps({'status': 'failed', 'reason': 'olcli auth failed', 'pdf_path': '', 'log_path': str(log_path), 'command_statuses': statuses}, indent=2))
        return 0

    if not (sync_dir / '.olcli.json').exists():
        pull = run(['npx', '-y', '@aloth/olcli', 'pull', args.project, str(sync_dir)])
        record(f'npx -y @aloth/olcli pull {args.project} {sync_dir}', pull)
        if pull.returncode != 0:
            log_path = run_dir / 'overleaf_build.log'
            log_path.write_text('\n\n'.join(logs), encoding='utf-8')
            print(json.dumps({'status': 'failed', 'reason': 'olcli pull failed (ensure the Overleaf project already exists and is accessible)', 'pdf_path': '', 'log_path': str(log_path), 'command_statuses': statuses}, indent=2))
            return 0

    for name in FILES_TO_SYNC:
        src = run_dir / name
        if src.exists():
            shutil.copy2(src, sync_dir / name)
    article_src = run_dir / 'article.tex'
    if article_src.exists():
        shutil.copy2(article_src, sync_dir / 'main.tex')
    for pattern in OPTIONAL_GLOBS:
        for src in run_dir.glob(pattern):
            if src.is_file():
                shutil.copy2(src, sync_dir / src.name)

    push = run(['npx', '-y', '@aloth/olcli', 'push', '--all', str(sync_dir)])
    record(f'npx -y @aloth/olcli push --all {sync_dir}', push)
    if push.returncode != 0:
        log_path = run_dir / 'overleaf_build.log'
        log_path.write_text('\n\n'.join(logs), encoding='utf-8')
        print(json.dumps({'status': 'failed', 'reason': 'olcli push failed', 'pdf_path': '', 'log_path': str(log_path), 'command_statuses': statuses}, indent=2))
        return 0

    out_pdf = run_dir / 'article.pdf'
    pdf = run(['npx', '-y', '@aloth/olcli', 'pdf', '-o', str(out_pdf)], cwd=sync_dir)
    record(f'npx -y @aloth/olcli pdf -o {out_pdf}', pdf)

    log_path = run_dir / 'overleaf_build.log'
    log_path.write_text('\n\n'.join(logs), encoding='utf-8')
    if pdf.returncode == 0 and out_pdf.exists():
        print(json.dumps({'status': 'ok', 'reason': 'compiled remotely with Overleaf via olcli', 'pdf_path': str(out_pdf), 'log_path': str(log_path), 'command_statuses': statuses, 'method': 'overleaf_olcli'}, indent=2))
    else:
        print(json.dumps({'status': 'failed', 'reason': 'Overleaf compilation did not produce article.pdf', 'pdf_path': '', 'log_path': str(log_path), 'command_statuses': statuses, 'method': 'overleaf_olcli'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
