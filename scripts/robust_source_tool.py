#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests

TOOLS_VENV = Path.home() / '.cache' / 'hermes-research-tools'
TOOLS_PY = TOOLS_VENV / 'bin' / 'python'
USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0 Safari/537.36'
)
DUCKDUCKGO_HTML = 'https://html.duckduckgo.com/html/'


def ensure_tools() -> None:
    if TOOLS_PY.exists():
        return
    TOOLS_VENV.parent.mkdir(parents=True, exist_ok=True)
    if TOOLS_VENV.exists() and not TOOLS_PY.exists():
        shutil.rmtree(TOOLS_VENV, ignore_errors=True)
    try:
        subprocess.run([sys.executable, '-m', 'venv', str(TOOLS_VENV)], check=True)
    except subprocess.CalledProcessError:
        shutil.rmtree(TOOLS_VENV, ignore_errors=True)
        subprocess.run([sys.executable, '-m', 'venv', str(TOOLS_VENV)], check=True)
    subprocess.run([str(TOOLS_PY), '-m', 'ensurepip', '--upgrade'], check=True)
    subprocess.run(
        [str(TOOLS_PY), '-m', 'pip', 'install', '-q', '-U', 'pip', 'ddgs', 'cloudscraper', 'beautifulsoup4'],
        check=True,
    )


def strip_tags(text: str) -> str:
    text = re.sub(r'<script.*?</script>', ' ', text, flags=re.I | re.S)
    text = re.sub(r'<style.*?</style>', ' ', text, flags=re.I | re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_result_url(href: str) -> str:
    href = html.unescape(href or '')
    if href.startswith('//'):
        return 'https:' + href
    if href.startswith('http://') or href.startswith('https://'):
        return href
    parsed = urlparse(href)
    if parsed.path.endswith('/l/') or parsed.path == '/l/':
        query = parse_qs(parsed.query)
        uddg = query.get('uddg') or query.get('rut')
        if uddg:
            return unquote(uddg[0])
    return href


def ddg_html_search(query: str, max_results: int) -> list[dict]:
    try:
        resp = requests.post(
            DUCKDUCKGO_HTML,
            data={'q': query},
            headers={'User-Agent': USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception:
        return []
    page = resp.text
    blocks = re.findall(r'<div class="result(?: results_links(?:_deep)?)?".*?</div>\s*</div>', page, flags=re.S)
    results = []
    seen = set()
    for block in blocks:
        title_match = re.search(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.S)
        if not title_match:
            continue
        raw_url, raw_title = title_match.groups()
        url = extract_result_url(raw_url)
        if not url or url in seen:
            continue
        seen.add(url)
        snippet_match = re.search(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>', block, flags=re.S)
        snippet_html = ''
        if snippet_match:
            snippet_html = next((g for g in snippet_match.groups() if g), '')
        results.append({'title': strip_tags(raw_title), 'url': url, 'snippet': strip_tags(snippet_html)})
        if len(results) >= max_results:
            break
    return results


def ddgs_search(query: str, max_results: int) -> list[dict]:
    ensure_tools()
    script = f'''
from ddgs import DDGS
import json
q = {query!r}
out = []
with DDGS() as ddgs:
    for r in ddgs.text(q, max_results={max_results}):
        out.append({{'title': r.get('title',''), 'url': r.get('href',''), 'snippet': r.get('body','')}})
print(json.dumps(out, ensure_ascii=False))
'''
    proc = subprocess.run([str(TOOLS_PY), '-c', script], capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    try:
        return json.loads(proc.stdout)
    except Exception:
        return []


def search(query: str, max_results: int) -> dict:
    results = ddgs_search(query, max_results)
    if not results:
        results = ddg_html_search(query, max_results)
    seen = set()
    clean = []
    for r in results:
        url = r.get('url', '')
        if not url or url in seen:
            continue
        seen.add(url)
        clean.append(r)
    return {'query': query, 'results': clean[:max_results]}


def extract_pdf_text(url: str, max_chars: int) -> dict:
    with tempfile.TemporaryDirectory() as td:
        pdf_path = Path(td) / 'doc.pdf'
        txt_path = Path(td) / 'doc.txt'
        resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=60, allow_redirects=True)
        resp.raise_for_status()
        pdf_path.write_bytes(resp.content)
        mutool = shutil.which('mutool')
        if not mutool:
            raise RuntimeError('mutool is required for PDF extraction but was not found')
        proc = subprocess.run([mutool, 'draw', '-q', '-F', 'txt', '-o', str(txt_path), str(pdf_path)], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f'mutool extraction failed: {proc.stderr.strip()}')
        text = txt_path.read_text(encoding='utf-8', errors='ignore')
        return {
            'url': url,
            'final_url': resp.url,
            'status_code': resp.status_code,
            'content_type': resp.headers.get('Content-Type', ''),
            'title': '',
            'text': text[:max_chars],
            'text_length': len(text),
            'method': 'requests+mutool',
        }


def fetch_html_with_cloudscraper(url: str) -> dict:
    ensure_tools()
    script = f'''
import json
import cloudscraper
scraper = cloudscraper.create_scraper(browser={{'browser':'chrome','platform':'linux','desktop':True}})
r = scraper.get({url!r}, timeout=60)
print(json.dumps({{'status_code': r.status_code, 'url': r.url, 'headers': dict(r.headers), 'text': r.text}}, ensure_ascii=False))
'''
    proc = subprocess.run([str(TOOLS_PY), '-c', script], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or 'cloudscraper failed')
    return json.loads(proc.stdout)


def fetch(url: str, max_chars: int) -> dict:
    headers = {'User-Agent': USER_AGENT, 'Accept': 'text/html,application/pdf,*/*'}
    try:
        resp = requests.get(url, headers=headers, timeout=45, allow_redirects=True)
        status = resp.status_code
        content_type = resp.headers.get('Content-Type', '')
        if status >= 400 and ('cloudflare' in resp.text.lower() or status in {403, 429}):
            raise RuntimeError(f'blocked {status}')
        if url.lower().endswith('.pdf') or 'application/pdf' in content_type.lower():
            return extract_pdf_text(resp.url if resp.url else url, max_chars)
        text = resp.text
        title_match = re.search(r'<title[^>]*>(.*?)</title>', text, flags=re.I | re.S)
        title = strip_tags(title_match.group(1)) if title_match else ''
        body = strip_tags(text)
        return {
            'url': url,
            'final_url': resp.url,
            'status_code': status,
            'content_type': content_type,
            'title': title,
            'text': body[:max_chars],
            'text_length': len(body),
            'method': 'requests',
        }
    except Exception:
        data = fetch_html_with_cloudscraper(url)
        content_type = data.get('headers', {}).get('Content-Type', '')
        if url.lower().endswith('.pdf') or 'application/pdf' in content_type.lower():
            return extract_pdf_text(data.get('url') or url, max_chars)
        text = data.get('text', '')
        title_match = re.search(r'<title[^>]*>(.*?)</title>', text, flags=re.I | re.S)
        title = strip_tags(title_match.group(1)) if title_match else ''
        body = strip_tags(text)
        return {
            'url': url,
            'final_url': data.get('url', url),
            'status_code': data.get('status_code', 0),
            'content_type': content_type,
            'title': title,
            'text': body[:max_chars],
            'text_length': len(body),
            'method': 'cloudscraper',
        }


def main() -> int:
    parser = argparse.ArgumentParser(description='Robust search/fetch helper for research skill')
    sub = parser.add_subparsers(dest='command', required=True)
    p_search = sub.add_parser('search')
    p_search.add_argument('--query', required=True)
    p_search.add_argument('--max-results', type=int, default=8)
    p_fetch = sub.add_parser('fetch')
    p_fetch.add_argument('--url', required=True)
    p_fetch.add_argument('--max-chars', type=int, default=12000)
    args = parser.parse_args()
    if args.command == 'search':
        result = search(args.query, args.max_results)
    else:
        result = fetch(args.url, args.max_chars)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
