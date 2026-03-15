#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

DUCKDUCKGO_HTML = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def strip_tags(text: str) -> str:
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_result_url(href: str) -> str:
    href = html.unescape(href or "")
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("http://") or href.startswith("https://"):
        return href
    parsed = urlparse(href)
    if parsed.path.endswith("/l/") or parsed.path == "/l/":
        query = parse_qs(parsed.query)
        uddg = query.get("uddg") or query.get("rut")
        if uddg:
            return unquote(uddg[0])
    return href


def search(query: str, max_results: int) -> dict:
    resp = requests.post(
        DUCKDUCKGO_HTML,
        data={"q": query},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    page = resp.text

    blocks = re.findall(r'<div class="result(?: results_links(?:_deep)?)?".*?</div>\s*</div>', page, flags=re.S)
    if not blocks:
        blocks = re.findall(r'<a rel="nofollow" class="result__a".*?</div>\s*</div>', page, flags=re.S)

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
        snippet_html = ""
        if snippet_match:
            snippet_html = next((g for g in snippet_match.groups() if g), "")
        results.append(
            {
                "title": strip_tags(raw_title),
                "url": url,
                "snippet": strip_tags(snippet_html),
            }
        )
        if len(results) >= max_results:
            break

    return {"query": query, "results": results}


def fetch(url: str, max_chars: int) -> dict:
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=30,
        allow_redirects=True,
    )
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    text = resp.text
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    title = strip_tags(title_match.group(1)) if title_match else ""
    body_text = strip_tags(text)
    return {
        "url": url,
        "final_url": resp.url,
        "status_code": resp.status_code,
        "content_type": content_type,
        "title": title,
        "text": body_text[:max_chars],
        "text_length": len(body_text),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DuckDuckGo HTML fallback search/fetch helper")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search")
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--max-results", type=int, default=5)

    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("--url", required=True)
    p_fetch.add_argument("--max-chars", type=int, default=12000)

    args = parser.parse_args()
    if args.command == "search":
        result = search(args.query, args.max_results)
    else:
        result = fetch(args.url, args.max_chars)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
