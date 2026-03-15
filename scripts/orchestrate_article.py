#!/home/mert/.hermes/hermes-agent/venv/bin/python
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import html
import json
import re
import shutil
import subprocess
import sys

import requests
from pathlib import Path
from typing import Any, Dict, List

import yaml

REPO_ROOT = Path.home() / '.hermes' / 'hermes-agent'
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from run_agent import AIAgent  # type: ignore

SKILL_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path.home() / 'hermes_article_pipeline'
RUNS_DIR = DATA_DIR / 'runs'
GLOBAL_LOG = DATA_DIR / 'quality_score_log.json'
FAILURE_TRACKER = DATA_DIR / 'failure_tracker.json'
LATEST_RUN = DATA_DIR / 'latest_run.json'
PROMPT_UPDATE_PROPOSALS = DATA_DIR / 'prompt_update_proposals.md'
HEURISTICS_FILE = SKILL_DIR / 'references' / 'editorial_heuristics.md'
PUSH_SCRIPT = SKILL_DIR / 'scripts' / 'push_github_repo.sh'
OVERLEAF_SCRIPT = SKILL_DIR / 'scripts' / 'overleaf_compile.py'
PUBLISH_HUB_SCRIPT = SKILL_DIR / 'scripts' / 'publish_hub.py'
ROUTING_FILE = SKILL_DIR / 'model_routing.yaml'


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(read_text(path))
    except Exception:
        return default


def save_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def load_yaml(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def load_template(name: str) -> str:
    return read_text(SKILL_DIR / 'templates' / name)


def load_routing() -> dict:
    return load_yaml(ROUTING_FILE)


def now_iso() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


def slugify(text: str, max_len: int = 48) -> str:
    text = re.sub(r'[^a-zA-Z0-9]+', '-', text.lower()).strip('-')
    text = re.sub(r'-+', '-', text)
    return (text[:max_len].rstrip('-') or 'untitled')


def normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value).strip()
    return [text] if text else []


def extract_json(text: str) -> Any:
    text = text.strip()
    fenced = re.findall(r'```json\s*(.*?)```', text, flags=re.S | re.I)
    candidates = fenced + [text]
    for candidate in candidates:
        candidate = candidate.strip()
        for start in ['{', '[']:
            idx = candidate.find(start)
            if idx == -1:
                continue
            snippet = candidate[idx:]
            try:
                return json.loads(snippet)
            except Exception:
                pass
            for end in range(len(snippet), 1, -1):
                frag = snippet[:end].strip()
                try:
                    return json.loads(frag)
                except Exception:
                    continue
    raise ValueError('Could not parse JSON from model output')


def call_agent(role: str, user_message: str, system_prompt: str) -> str:
    routing = load_routing()
    cfg = routing['roles'][role]
    provider = routing.get('provider', 'openai-codex')
    model = cfg['model']
    fallback_model = cfg.get('fallback_model')
    toolsets = cfg.get('toolsets')
    max_iterations = cfg.get('max_iterations', 8)

    kwargs: Dict[str, Any] = {
        'provider': provider,
        'model': model,
        'quiet_mode': True,
        'skip_context_files': True,
        'skip_memory': True,
        'enabled_toolsets': toolsets,
        'max_iterations': max_iterations,
        'platform': 'cli',
    }
    if fallback_model:
        kwargs['fallback_model'] = {'provider': provider, 'model': fallback_model}

    agent = AIAgent(**kwargs)
    result = agent.run_conversation(user_message=user_message, system_message=system_prompt)
    return (result.get('final_response') or '').strip()


def infer_year(*values: str) -> str:
    for value in values:
        match = re.search(r'(19|20)\d{2}', value or '')
        if match:
            return match.group(0)
    return 'unknown'


def parse_meta_tags(raw_html: str) -> dict[str, List[str]]:
    tags: dict[str, List[str]] = {}
    pattern = re.compile(r'<meta[^>]+(?:name|property)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\'][^>]*>', re.I)
    for key, value in pattern.findall(raw_html or ''):
        key = key.strip().lower()
        value = html.unescape(value.strip())
        if value:
            tags.setdefault(key, []).append(value)
    return tags


def infer_evidence_access(source: dict, resp: requests.Response | None = None) -> str:
    existing = str(source.get('evidence_access', '') or '').strip().lower()
    if existing in {'full_text', 'abstract_only', 'metadata_only', 'news_report'}:
        return existing
    url = str(source.get('url', '') or '').lower()
    content_type = (resp.headers.get('Content-Type', '') if resp is not None else str(source.get('_content_type', ''))).lower()
    content_length = len(resp.text or '') if resp is not None else int(source.get('_content_length', 0) or 0)
    if url.endswith('.pdf') or 'application/pdf' in content_type:
        return 'full_text'
    if 'arxiv.org/html/' in url or 'github.com/' in url or 'docs.polymarket.com/' in url:
        return 'full_text' if content_length > 1500 else 'metadata_only'
    if '/abs/' in url or '/science/article/abs/' in url:
        return 'abstract_only'
    if 'news' in str(source.get('domain_type', '')).lower():
        return 'news_report'
    return 'full_text' if content_length > 1500 else 'metadata_only'


def infer_support_strength(source: dict) -> str:
    existing = str(source.get('support_strength', '') or '').strip().lower()
    if existing in {'direct', 'indirect', 'contextual'}:
        return existing
    why = str(source.get('why_relevant', '')).lower()
    key_text = ' '.join(normalize_list(source.get('key_points'))).lower()
    joined = f'{why} {key_text}'
    if any(k in joined for k in ['direct', 'primary technical reference', 'highly aligned', 'methodological precedent', 'data-availability claim']):
        return 'direct'
    if any(k in joined for k in ['context', 'baseline', 'historical context', 'contextual']):
        return 'contextual'
    return 'indirect'


def summarize_source_quality(sources: List[dict]) -> dict:
    counts = {
        'high_credibility': 0,
        'credible_accessible': 0,
        'direct_support': 0,
        'full_text': 0,
        'protocol_ready': 0,
    }
    for source in sources:
        credibility = str(source.get('credibility_tier', '')).lower()
        access = infer_evidence_access(source)
        support = infer_support_strength(source)
        source['evidence_access'] = access
        source['support_strength'] = support
        if credibility == 'high':
            counts['high_credibility'] += 1
        if credibility in {'high', 'medium'} and access in {'full_text', 'abstract_only', 'news_report'}:
            counts['credible_accessible'] += 1
        if support == 'direct':
            counts['direct_support'] += 1
        if access == 'full_text':
            counts['full_text'] += 1
        if credibility in {'high', 'medium'} and support == 'direct' and access in {'full_text', 'abstract_only', 'news_report'}:
            counts['protocol_ready'] += 1
    counts['can_proceed_as_protocol'] = (
        counts['high_credibility'] >= 2
        and counts['protocol_ready'] >= 2
        and counts['credible_accessible'] >= 4
    )
    return counts


def enrich_source_metadata(source: dict) -> dict:
    url = str(source.get('url', '')).strip()
    if not url:
        return source
    try:
        resp = requests.get(url, timeout=20, headers={'User-Agent': 'HermesAgent/1.0'})
        resp.raise_for_status()
    except Exception:
        return source

    source['_fetch_status'] = resp.status_code
    source['_content_type'] = resp.headers.get('Content-Type', '')
    source['_content_length'] = len(resp.text or '')
    source['evidence_access'] = infer_evidence_access(source, resp)

    meta = parse_meta_tags(resp.text)
    authors = meta.get('citation_author', []) or meta.get('dc.creator', [])
    title = (meta.get('citation_title', []) or meta.get('og:title', []) or meta.get('dc.title', []))
    date_candidates = (
        meta.get('citation_publication_date', [])
        or meta.get('citation_date', [])
        or meta.get('article:published_time', [])
        or meta.get('dc.date', [])
    )

    if title and not source.get('title'):
        source['title'] = title[0]
    if authors:
        source['authors'] = authors
    if date_candidates:
        inferred = infer_year(' '.join(date_candidates))
        if inferred != 'unknown':
            source['published_date'] = date_candidates[0]
    return source


def organization_from_domain(domain: str) -> str:
    domain = (domain or '').lower()
    if 'aclanthology.org' in domain:
        return 'ACL Anthology'
    if 'neurips.cc' in domain or 'proceedings.neurips.cc' in domain:
        return 'NeurIPS Proceedings'
    if 'arxiv.org' in domain:
        return 'arXiv'
    if 'pubmed' in domain or 'nih.gov' in domain:
        return 'PubMed/NIH'
    if domain:
        return domain
    return 'Unknown Organization'


def build_bib_key(title: str, published_date: str, domain: str, url: str = '') -> str:
    year = infer_year(published_date, url)
    title_slug = slugify(title, max_len=22).replace('-', '')[:18] or 'source'
    domain_slug = slugify((domain or 'web').split('.')[0], max_len=8).replace('-', '')[:8]
    year_part = year if year != 'unknown' else 'nd'
    return f'{title_slug}{year_part}{domain_slug}'


def bibtex_for_source(source: dict, accessed: str) -> str:
    title = str(source.get('title', 'Untitled source')).replace('{', '\\{').replace('}', '\\}')
    url = str(source.get('url', ''))
    domain = str(source.get('domain', 'Unknown'))
    published_date = str(source.get('published_date', ''))
    year = infer_year(published_date, url)
    key = source.get('bibtex_key') or build_bib_key(title, published_date, domain, url)
    raw_authors = normalize_list(source.get('authors'))
    if raw_authors:
        author_value = ' and '.join(a.replace('{', '\\{').replace('}', '\\}') for a in raw_authors)
    else:
        author_value = organization_from_domain(domain).replace('{', '\\{').replace('}', '\\}')
    note = f"Credibility tier: {source.get('credibility_tier', 'unknown')}. Accessed {accessed}."
    lines = [
        f"@misc{{{key},",
        f"  title = {{{title}}},",
        f"  author = {{{author_value}}},",
    ]
    if year != 'unknown':
        lines.append(f"  year = {{{year}}},")
    lines.append(f"  url = {{{url}}},")
    lines.append(f"  note = {{{note}}}")
    lines.append("}")
    return "\n".join(lines)


def source_issue_count(review: dict) -> int:
    return len(normalize_list(review.get('must_fix_before_publish')))


def normalize_score(value: Any) -> float:
    try:
        score = float(value)
    except Exception:
        return 0.0
    if score > 10:
        score = score / 10.0
    if score < 0:
        score = 0.0
    if score > 10:
        score = 10.0
    return score


def latex_to_plain_text(latex: str) -> str:
    text = latex or ''
    text = re.sub(r'%.*', ' ', text)
    text = re.sub(r'\\begin\{[^}]+\}|\\end\{[^}]+\}', ' ', text)
    text = re.sub(r'\\(?:cite|citet|citep|citeauthor|citeyear)\*?(?:\[[^\]]*\])?\{[^}]*\}', ' ', text)
    text = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?', r' \1 ', text)
    text = re.sub(r'[{}]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def manuscript_metrics(latex: str, bibtex_keys: List[str]) -> dict:
    plain = latex_to_plain_text(latex)
    word_count = len(re.findall(r"\b[\w'-]+\b", plain))
    section_count = len(re.findall(r'\\section\{', latex or ''))
    subsection_count = len(re.findall(r'\\subsection\{', latex or ''))
    citation_count = 0
    for key in bibtex_keys:
        if key:
            citation_count += len(re.findall(rf'\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])?\{{[^}}]*\b{re.escape(key)}\b[^}}]*\}}', latex or ''))
    lowered = plain.lower()
    missing_elements: List[str] = []
    required_patterns = {
        'abstract': r'\\begin\{abstract\}|\\abstract\{',
        'introduction': r'\\section\{[^}]*introduction[^}]*\}',
        'related_work': r'\\section\{[^}]*(related literature|related work|background)[^}]*\}',
        'methodology': r'\\section\{[^}]*(method|methodology|identification strategy|analytical framework)[^}]*\}',
        'data': r'\\section\{[^}]*(data|sources|data and source construction)[^}]*\}',
        'limitations': r'\\section\{[^}]*(limitations|threats to validity|robustness)[^}]*\}',
        'discussion': r'\\section\{[^}]*(discussion|implications)[^}]*\}',
        'conclusion': r'\\section\{[^}]*conclusion[^}]*\}',
    }
    for name, pattern in required_patterns.items():
        if not re.search(pattern, latex or '', flags=re.I):
            missing_elements.append(name)
    return {
        'word_count': word_count,
        'section_count': section_count,
        'subsection_count': subsection_count,
        'citation_count': citation_count,
        'citation_density_per_1000_words': round((citation_count / max(word_count, 1)) * 1000, 2),
        'missing_elements': missing_elements,
        'plain_text_preview': plain[:500],
        'looks_publishable_length': word_count >= 3500,
    }


def deterministic_gate(reviews: List[dict], llm_gate: dict, max_iterations: int, current_iteration: int, manuscript_checks: dict | None = None) -> dict:
    manuscript_checks = manuscript_checks or {}
    avg_score = sum(normalize_score(r.get('overall_score', 0)) for r in reviews) / max(1, len(reviews))
    source_review = next((r for r in reviews if r.get('reviewer') == 'source_verifier'), {})
    source_blockers = source_issue_count(source_review)
    pass_count = sum(1 for r in reviews if bool(r.get('pass')))
    all_pass = pass_count == len(reviews)

    blocking_reasons: List[str] = []
    if manuscript_checks.get('word_count', 0) < 3500:
        blocking_reasons.append('manuscript_too_short')
    if manuscript_checks.get('section_count', 0) < 7:
        blocking_reasons.append('too_few_sections')
    if manuscript_checks.get('subsection_count', 0) < 3:
        blocking_reasons.append('too_few_subsections')
    if manuscript_checks.get('citation_density_per_1000_words', 0) < 2.5:
        blocking_reasons.append('low_citation_density')
    for missing in manuscript_checks.get('missing_elements', []):
        blocking_reasons.append(f'missing_{missing}')

    has_structure_blockers = bool(blocking_reasons)
    strong_consensus = pass_count >= 2 and avg_score >= 8.0 and source_blockers == 0 and not has_structure_blockers
    passed = all_pass and avg_score >= 7.5 and source_blockers == 0 and not has_structure_blockers

    if passed:
        decision = 'pass'
    elif llm_gate.get('decision') == 'pass' and strong_consensus:
        decision = 'pass'
    elif current_iteration >= max_iterations and strong_consensus:
        decision = 'pass'
    elif current_iteration >= max_iterations:
        decision = 'warn'
    else:
        decision = 'revise'
    return {
        'decision': decision,
        'average_score': round(avg_score, 2),
        'source_blockers': source_blockers,
        'pass_count': pass_count,
        'all_pass': all_pass,
        'llm_quality_score': float(llm_gate.get('quality_score', 0) or 0),
        'llm_gate': llm_gate,
        'manuscript_checks': manuscript_checks,
        'blocking_reasons': blocking_reasons,
    }


def classify_failure_text(text: str) -> List[str]:
    text = text.lower()
    kinds: List[str] = []
    if any(k in text for k in ['source', 'citation', 'credib', 'unsupported', 'hallucinat']):
        kinds.append('sourcing')
    if any(k in text for k in ['shallow', 'depth', 'nuance', 'superficial', 'too short', 'underdeveloped', 'thin']):
        kinds.append('depth')
    if any(k in text for k in ['tone', 'formal', 'casual', 'voice', 'style']):
        kinds.append('tone')
    if any(k in text for k in ['structure', 'organization', 'flow', 'intro', 'conclusion', 'methodology', 'related work', 'limitations', 'subsection']):
        kinds.append('structure')
    if any(k in text for k in ['readability', 'dense', 'boring', 'engaging', 'clear']):
        kinds.append('readability')
    return sorted(set(kinds))


def classify_failures_from_reviews(reviews: List[dict]) -> List[str]:
    chunks: List[str] = []
    for review in reviews:
        chunks.extend(normalize_list(review.get('issues_major')))
        chunks.extend(normalize_list(review.get('issues_minor')))
        chunks.extend(normalize_list(review.get('must_fix_before_publish')))
    return classify_failure_text('\n'.join(chunks))


def append_quality_log(entry: dict) -> None:
    log = load_json(GLOBAL_LOG, [])
    log.append(entry)
    save_json(GLOBAL_LOG, log)


def update_failure_tracker(run_id: str, failure_types: List[str]) -> dict:
    tracker = load_json(FAILURE_TRACKER, {})
    for ft in failure_types:
        bucket = tracker.setdefault(ft, {'count': 0, 'runs': []})
        bucket['count'] += 1
        bucket['runs'].append(run_id)
        bucket['runs'] = bucket['runs'][-10:]
    save_json(FAILURE_TRACKER, tracker)
    return tracker


def maybe_write_prompt_proposals(tracker: dict) -> None:
    proposals = {
        'sourcing': 'Strengthen the writer and source-verifier prompts to require denser citation coverage and stronger caveat language for weak evidence.',
        'depth': 'Expand the writer prompt to require deeper subsection development, explicit nuance, and stronger comparative analysis.',
        'tone': 'Refine the writer and general-reader prompts to align tone with stored user preferences and avoid mismatched formality.',
        'structure': 'Add stronger outline and transition requirements to the writer prompt and tighter structural checks to the academic/general reviewers.',
        'readability': 'Tighten readability checks and require clearer openings, shorter paragraphs where useful, and more accessible explanations.',
    }
    lines = ['# Prompt Update Proposals', '']
    triggered = False
    for key, note in proposals.items():
        count = int(tracker.get(key, {}).get('count', 0))
        if count >= 3:
            triggered = True
            lines.append(f'## {key}')
            lines.append(f'- Recurrence count: {count}')
            lines.append(f'- Proposal: {note}')
            lines.append('')
    if triggered:
        write_text(PROMPT_UPDATE_PROPOSALS, '\n'.join(lines).rstrip() + '\n')


def update_heuristics(run_id: str, decision: str, failure_types: List[str], extra_notes: List[str] | None = None) -> None:
    existing = read_text(HEURISTICS_FILE).rstrip() if HEURISTICS_FILE.exists() else '# Editorial Heuristics'
    extra_notes = extra_notes or []
    lines = [
        '',
        f'## Run {run_id} ({now_iso()})',
        f'- Final decision: {decision}',
        f'- Failure categories: {", ".join(failure_types) if failure_types else "none"}',
    ]
    for note in extra_notes:
        lines.append(f'- {note}')
    write_text(HEURISTICS_FILE, existing + '\n' + '\n'.join(lines) + '\n')


def summarize_reviews(iterations: List[dict]) -> str:
    lines = ['# Review Summary', '']
    for item in iterations:
        gate = item['gate']
        lines.append(f"## Iteration {item['iteration']}")
        lines.append(f"- Average score: {gate['average_score']}")
        lines.append(f"- Decision: {gate['decision']}")
        for review in item['reviews']:
            lines.append(f"- {review['reviewer']}: score={review['overall_score']}, pass={review['pass']}")
            for issue in normalize_list(review.get('must_fix_before_publish'))[:5]:
                lines.append(f"  - must-fix: {issue}")
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def make_readme(meta: dict) -> str:
    lines = [
        f"# {meta['title']}",
        '',
        '## What this article covers',
        meta['topic'],
        '',
        '## Hypothesis question',
        meta['hypothesis'],
        '',
        '## Research topics',
    ]
    for item in meta.get('research_topics', []):
        lines.append(f'- {item}')
    lines.extend(['', '## Pipeline workflow', 'research -> write -> review -> revise -> finalize', '', '## Models used by role'])
    for role, model in meta['models_used'].items():
        lines.append(f'- {role}: {model}')
    lines.extend(['', '## Review iterations completed', str(meta['iterations']), '', '## Source credibility summary', json.dumps(meta['credibility_summary'], indent=2)])
    manuscript = meta.get('manuscript_checks', {}) or {}
    if manuscript:
        lines.extend([
            '',
            '## Manuscript depth checks',
            f"- Word count: {manuscript.get('word_count', 0)}",
            f"- Section count: {manuscript.get('section_count', 0)}",
            f"- Subsection count: {manuscript.get('subsection_count', 0)}",
            f"- Citation count: {manuscript.get('citation_count', 0)}",
            f"- Citation density per 1000 words: {manuscript.get('citation_density_per_1000_words', 0)}",
            f"- Missing required elements: {', '.join(manuscript.get('missing_elements', [])) or 'none'}",
        ])
    if meta.get('pdf_status') == 'ok':
        lines.extend(['', '## PDF artifact', f"Generated successfully: {meta.get('pdf_path', 'article.pdf')}"])
    elif meta.get('pdf_status') == 'disabled':
        lines.extend(['', '## PDF artifact', 'Local PDF compilation was intentionally disabled for this run to avoid VPS load. Deliver article.tex and references.bib as the primary outputs.'])
    else:
        lines.extend(['', '## PDF artifact', f"Not generated. Reason: {meta.get('pdf_reason', 'unknown')}"])
    return '\n'.join(lines).rstrip() + '\n'


def latest_run_dir() -> Path | None:
    data = load_json(LATEST_RUN, None)
    if not data:
        return None
    run_dir = Path(data.get('run_dir', ''))
    return run_dir if run_dir.exists() else None


def shell_run(cmd: List[str], cwd: Path | None = None) -> str:
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'command failed')
    return result.stdout.strip()


def compile_latex_pdf(run_dir: Path) -> dict:
    article_path = run_dir / 'article.tex'
    if not article_path.exists():
        return {'status': 'skipped', 'reason': 'article.tex missing'}
    if not shutil.which('pdflatex'):
        return {'status': 'skipped', 'reason': 'pdflatex not installed'}
    if not shutil.which('bibtex'):
        return {'status': 'skipped', 'reason': 'bibtex not installed'}

    commands = [
        ['pdflatex', '-interaction=nonstopmode', 'article.tex'],
        ['bibtex', 'article'],
        ['pdflatex', '-interaction=nonstopmode', 'article.tex'],
        ['pdflatex', '-interaction=nonstopmode', 'article.tex'],
    ]
    log_parts: List[str] = []
    statuses: List[dict] = []
    for cmd in commands:
        proc = subprocess.run(cmd, cwd=str(run_dir), capture_output=True, text=True)
        statuses.append({'command': ' '.join(cmd), 'returncode': proc.returncode})
        log_parts.append(f"$ {' '.join(cmd)}\n{proc.stdout}\n{proc.stderr}")
    write_text(run_dir / 'latex_build.log', '\n\n'.join(log_parts))
    pdf_path = run_dir / 'article.pdf'
    if pdf_path.exists():
        return {'status': 'ok', 'pdf_path': str(pdf_path), 'log_path': str(run_dir / 'latex_build.log'), 'command_statuses': statuses}
    return {'status': 'failed', 'reason': 'article.pdf was not produced', 'log_path': str(run_dir / 'latex_build.log'), 'command_statuses': statuses}


def disabled_pdf_result(reason: str = 'disabled by configuration') -> dict:
    return {
        'status': 'disabled',
        'reason': reason,
        'pdf_path': '',
        'log_path': '',
        'command_statuses': [],
    }


def compile_overleaf_pdf(run_dir: Path) -> dict:
    if not OVERLEAF_SCRIPT.exists():
        return disabled_pdf_result('overleaf compile script is missing')
    proc = subprocess.run(
        [sys.executable, str(OVERLEAF_SCRIPT), '--run-dir', str(run_dir)],
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or '').strip()
    try:
        return json.loads(output or '{}')
    except Exception:
        return {
            'status': 'failed',
            'reason': proc.stderr.strip() or output or 'overleaf compile helper returned invalid output',
            'pdf_path': '',
            'log_path': '',
            'command_statuses': [],
        }


def publish_hub(run_dir: Path, github_url: str, skip_netlify: bool = False) -> dict:
    if not PUBLISH_HUB_SCRIPT.exists():
        return {'status': 'skipped', 'reason': 'publish hub script is missing'}
    cmd = [sys.executable, str(PUBLISH_HUB_SCRIPT), '--run-dir', str(run_dir)]
    if github_url:
        cmd.extend(['--paper-github-url', github_url])
    if skip_netlify:
        cmd.append('--skip-netlify')
    proc = subprocess.run(cmd, capture_output=True, text=True)
    output = (proc.stdout or '').strip()
    try:
        return json.loads(output or '{}')
    except Exception:
        return {'status': 'failed', 'reason': proc.stderr.strip() or output or 'publish hub helper returned invalid output'}


def prepare_run(title: str) -> tuple[str, Path]:
    ensure_dirs()
    stamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    run_id = f"{stamp}_{slugify(title)}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_id, run_dir


def run_pipeline(args: argparse.Namespace) -> int:
    run_id, run_dir = prepare_run(args.title)
    request = {
        'run_id': run_id,
        'created_at': now_iso(),
        'topic': args.topic,
        'hypothesis': args.hypothesis,
        'title': args.title,
        'tone': args.tone,
        'audience': args.audience,
        'length': args.length,
        'max_iterations': args.max_iterations,
    }
    save_json(run_dir / 'request.json', request)

    research_raw = call_agent('research', json.dumps(request, indent=2), load_template('research_prompt.md'))
    write_text(run_dir / 'research_raw.txt', research_raw + '\n')
    research = extract_json(research_raw)
    sources = research.get('sources', [])
    for source in sources:
        enrich_source_metadata(source)
        source['bibtex_key'] = build_bib_key(source.get('title', ''), source.get('published_date', ''), source.get('domain', ''), source.get('url', ''))

    source_quality = summarize_source_quality(sources)
    save_json(run_dir / 'research_sources.json', sources)
    save_json(run_dir / 'source_quality.json', source_quality)

    research_brief = str(research.get('research_brief_markdown', '')).strip()
    if source_quality.get('can_proceed_as_protocol') and research.get('status') == 'insufficient_sources':
        research_brief = (
            research_brief
            + '\n\nProtocol fallback note\n'
            + '- This run proceeds as a protocol/evidence-synthesis manuscript because enough credible/directly accessible sources were found to specify design and reproducibility details, even though the source pack is still not strong enough for confident publication-style causal claims.\n'
            + '- Strong causal claims must remain explicitly downscoped unless later runs recover more full-text primary support.\n'
        ).strip()
    write_text(run_dir / 'research_brief.md', research_brief + '\n')
    research['research_brief_markdown'] = research_brief

    high_count = int(research.get('credibility_summary', {}).get('high', 0) or 0)
    if (research.get('status') == 'insufficient_sources' or high_count < 3) and not source_quality.get('can_proceed_as_protocol'):
        summary = {
            'status': 'halted',
            'warning': research.get('warning', 'Insufficient high-credibility sources.'),
            'run_dir': str(run_dir),
            'high_credibility_sources': high_count,
            'source_quality': source_quality,
        }
        save_json(run_dir / 'final_summary.json', summary)
        save_json(LATEST_RUN, {'run_id': run_id, 'run_dir': str(run_dir), 'status': 'halted'})
        print(json.dumps(summary, indent=2))
        return 0

    accessed = dt.datetime.now().strftime('%Y-%m-%d')
    bib_entries = [bibtex_for_source(source, accessed) for source in sources]
    write_text(run_dir / 'references.bib', '\n\n'.join(bib_entries).strip() + '\n')

    writer_input = {
        'title': args.title,
        'topic': args.topic,
        'hypothesis': args.hypothesis,
        'tone': args.tone,
        'audience': args.audience,
        'length': args.length,
        'research_topics': research.get('research_topics', []),
        'outline': research.get('suggested_outline', []),
        'research_brief_markdown': research.get('research_brief_markdown', ''),
        'source_quality': source_quality,
        'sources': sources,
        'bibtex_keys': [source['bibtex_key'] for source in sources],
    }

    writer_raw = call_agent('writer', json.dumps(writer_input, indent=2), load_template('writer_prompt.md'))
    write_text(run_dir / 'writer_v1_raw.txt', writer_raw + '\n')
    writer_json = extract_json(writer_raw)
    draft_tex = writer_json['article_tex']
    write_text(run_dir / 'draft_v1.tex', draft_tex.strip() + '\n')
    current_manuscript_checks = manuscript_metrics(draft_tex, [source['bibtex_key'] for source in sources])
    save_json(run_dir / 'manuscript_checks_v1.json', current_manuscript_checks)

    iterations: List[dict] = []
    final_gate: dict | None = None
    final_decision = 'warn'

    reviewer_templates = {
        'review_academic': 'reviewer_academic.md',
        'review_general': 'reviewer_general.md',
        'review_source': 'reviewer_source.md',
    }

    for iteration in range(1, args.max_iterations + 1):
        review_payload = json.dumps({
            'title': args.title,
            'hypothesis': args.hypothesis,
            'research_brief_markdown': research.get('research_brief_markdown', ''),
            'source_quality': source_quality,
            'sources': sources,
            'draft_tex': draft_tex,
        }, indent=2)

        review_results: List[dict] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(call_agent, role, review_payload, load_template(template)): role for role, template in reviewer_templates.items()}
            for future in concurrent.futures.as_completed(futures):
                role = futures[future]
                raw = future.result()
                write_text(run_dir / f'{role}_v{iteration}_raw.txt', raw + '\n')
                parsed = extract_json(raw)
                review_results.append(parsed)
                save_json(run_dir / f"{parsed['reviewer']}_v{iteration}.json", parsed)

        review_results.sort(key=lambda x: x.get('reviewer', ''))

        synth_raw = call_agent('synthesizer', json.dumps({'iteration': iteration, 'reviews': review_results}, indent=2), load_template('synthesizer_prompt.md'))
        write_text(run_dir / f'synthesizer_v{iteration}_raw.txt', synth_raw + '\n')
        synth = extract_json(synth_raw)
        write_text(run_dir / f'revision_brief_v{iteration}.md', str(synth.get('revision_brief_markdown', '')).strip() + '\n')

        current_manuscript_checks = manuscript_metrics(draft_tex, [source['bibtex_key'] for source in sources])
        save_json(run_dir / f'manuscript_checks_v{iteration}.json', current_manuscript_checks)
        gate_raw = call_agent('quality_gate', json.dumps({'iteration': iteration, 'reviews': review_results, 'revision_brief': synth, 'manuscript_checks': current_manuscript_checks}, indent=2), load_template('quality_gate_prompt.md'))
        write_text(run_dir / f'quality_gate_v{iteration}_raw.txt', gate_raw + '\n')
        llm_gate = extract_json(gate_raw)
        gate = deterministic_gate(review_results, llm_gate, args.max_iterations, iteration, current_manuscript_checks)
        save_json(run_dir / f'quality_gate_v{iteration}.json', gate)

        iterations.append({'iteration': iteration, 'reviews': review_results, 'synth': synth, 'gate': gate})
        final_gate = gate
        final_decision = gate['decision']

        if gate['decision'] == 'pass':
            break
        if iteration >= args.max_iterations:
            break

        unresolved_must_fix = synth.get('unresolved_must_fix', synth.get('must_fix', []))
        review_must_fix = []
        for review in review_results:
            review_must_fix.extend(normalize_list(review.get('must_fix_before_publish')))
        revision_input = {
            'title': args.title,
            'topic': args.topic,
            'hypothesis': args.hypothesis,
            'tone': args.tone,
            'audience': args.audience,
            'length': args.length,
            'research_brief_markdown': research.get('research_brief_markdown', ''),
            'source_quality': source_quality,
            'sources': sources,
            'bibtex_keys': [source['bibtex_key'] for source in sources],
            'prior_draft_tex': draft_tex,
            'revision_brief_markdown': synth.get('revision_brief_markdown', ''),
            'must_fix': synth.get('must_fix', []),
            'unresolved_must_fix': unresolved_must_fix,
            'prioritized_checklist': synth.get('prioritized_checklist', []),
            'reviewer_must_fix_raw': review_must_fix,
            'recommended_improvements': synth.get('recommended_improvements', []),
            'manuscript_type': 'evidence synthesis and protocol proposal',
            'revision_instruction': 'Resolve unresolved_must_fix items directly in the prose and structure. Remove ambiguity rather than layering extra caveats. Preserve readability while making the manuscript type explicit.',
        }
        writer_raw = call_agent('writer', json.dumps(revision_input, indent=2), load_template('writer_prompt.md'))
        write_text(run_dir / f'writer_v{iteration + 1}_raw.txt', writer_raw + '\n')
        writer_json = extract_json(writer_raw)
        draft_tex = writer_json['article_tex']
        write_text(run_dir / f'draft_v{iteration + 1}.tex', draft_tex.strip() + '\n')
        current_manuscript_checks = manuscript_metrics(draft_tex, [source['bibtex_key'] for source in sources])
        save_json(run_dir / f'manuscript_checks_v{iteration + 1}.json', current_manuscript_checks)

    final_manuscript_checks = manuscript_metrics(draft_tex, [source['bibtex_key'] for source in sources])
    save_json(run_dir / 'manuscript_checks_final.json', final_manuscript_checks)
    write_text(run_dir / 'article.tex', draft_tex.strip() + '\n')
    if args.compile_pdf:
        pdf_result = compile_latex_pdf(run_dir)
    elif not args.skip_overleaf_compile:
        pdf_result = compile_overleaf_pdf(run_dir)
        if pdf_result.get('status') == 'skipped':
            pdf_result = disabled_pdf_result(pdf_result.get('reason', 'overleaf compilation not configured'))
    else:
        pdf_result = disabled_pdf_result('local PDF compilation disabled and overleaf compilation skipped for this run')
    write_text(run_dir / 'review_summary.md', summarize_reviews(iterations))

    failure_types = classify_failures_from_reviews(iterations[-1]['reviews']) if iterations else []
    failure_types = sorted(set(failure_types + classify_failure_text('\n'.join((final_gate or {}).get('blocking_reasons', [])))))
    tracker = update_failure_tracker(run_id, failure_types)
    maybe_write_prompt_proposals(tracker)
    update_heuristics(run_id, final_decision, failure_types, [
        f"Average score: {final_gate['average_score'] if final_gate else 'n/a'}",
        f"Source blockers: {final_gate['source_blockers'] if final_gate else 'n/a'}",
    ])

    models_used = {role: cfg.get('model') for role, cfg in load_routing().get('roles', {}).items()}
    readme = make_readme({
        'title': args.title,
        'topic': args.topic,
        'hypothesis': args.hypothesis,
        'research_topics': research.get('research_topics', []),
        'models_used': models_used,
        'iterations': len(iterations),
        'credibility_summary': research.get('credibility_summary', {}),
        'pdf_status': pdf_result.get('status'),
        'pdf_path': pdf_result.get('pdf_path', ''),
        'pdf_reason': pdf_result.get('reason', ''),
        'manuscript_checks': final_manuscript_checks,
    })
    write_text(run_dir / 'README.md', readme)

    run_eval = {
        'run_id': run_id,
        'decision': final_decision,
        'average_score': final_gate['average_score'] if final_gate else None,
        'source_blockers': final_gate['source_blockers'] if final_gate else None,
        'failure_types': failure_types,
        'threshold_note': (final_gate or {}).get('llm_gate', {}).get('threshold_adjustment_note', ''),
        'pdf_result': pdf_result,
        'manuscript_checks': final_manuscript_checks,
        'blocking_reasons': (final_gate or {}).get('blocking_reasons', []),
        'improvement_goal': 'Each article should improve over time through heuristics accumulation and feedback logging.',
    }
    save_json(run_dir / 'run_evaluation.md', run_eval)

    append_quality_log({
        'run_id': run_id,
        'timestamp': now_iso(),
        'title': args.title,
        'quality_score': final_gate['average_score'] if final_gate else 0,
        'decision': final_decision,
        'failure_types': failure_types,
    })

    github_url = ''
    if not args.skip_github_push:
        repo_name = f"research-{slugify(args.title)}-{dt.datetime.now().strftime('%Y-%m-%d')}"
        try:
            github_url = shell_run(['bash', str(PUSH_SCRIPT), str(run_dir), repo_name, 'emomert'])
        except Exception as e:
            github_url = f'push_failed: {e}'

    publishing_hub = {'status': 'skipped', 'reason': 'publishing hub skipped for this run'}
    if not args.skip_publishing_hub:
        publishing_hub = publish_hub(run_dir, github_url, skip_netlify=args.skip_netlify_deploy)

    latest = {
        'run_id': run_id,
        'run_dir': str(run_dir),
        'title': args.title,
        'topic': args.topic,
        'decision': final_decision,
        'pdf_result': pdf_result,
        'updated_at': now_iso(),
    }
    if github_url:
        latest['github_url'] = github_url
    if publishing_hub:
        latest['publishing_hub'] = publishing_hub
    save_json(LATEST_RUN, latest)

    summary = {
        'status': 'completed',
        'run_id': run_id,
        'run_dir': str(run_dir),
        'article_tex': str(run_dir / 'article.tex'),
        'article_pdf': str(run_dir / 'article.pdf') if (run_dir / 'article.pdf').exists() else '',
        'review_summary': str(run_dir / 'review_summary.md'),
        'references_bib': str(run_dir / 'references.bib'),
        'pdf_result': pdf_result,
        'iterations': len(iterations),
        'final_decision': final_decision,
        'quality_score': final_gate['average_score'] if final_gate else 0,
        'manuscript_checks': final_manuscript_checks,
        'blocking_reasons': (final_gate or {}).get('blocking_reasons', []),
    }
    if github_url:
        summary['github_url'] = github_url
    if publishing_hub:
        summary['publishing_hub'] = publishing_hub
    print(json.dumps(summary, indent=2))
    return 0


def handle_feedback(args: argparse.Namespace) -> int:
    ensure_dirs()
    run_dir = Path(args.run_dir) if args.run_dir else latest_run_dir()
    if not run_dir or not run_dir.exists():
        print(json.dumps({'status': 'error', 'message': 'No latest run found.'}, indent=2))
        return 1

    feedback_text = args.message.strip()
    record = {
        'timestamp': now_iso(),
        'message': feedback_text,
        'detected_categories': classify_failure_text(feedback_text),
    }
    log = load_json(run_dir / 'feedback_log.json', [])
    log.append(record)
    save_json(run_dir / 'feedback_log.json', log)

    tracker = update_failure_tracker(run_dir.name, record['detected_categories'])
    maybe_write_prompt_proposals(tracker)
    update_heuristics(run_dir.name, 'feedback', record['detected_categories'], [f'User feedback: {feedback_text}'])

    preference_notes: List[str] = []
    lowered = feedback_text.lower()
    if 'shallow' in lowered or 'deeper' in lowered or 'more depth' in lowered:
        preference_notes.append('prefers deeper and more nuanced analysis')
    if 'citation' in lowered or 'source' in lowered:
        preference_notes.append('wants stronger citation density and sourcing clarity')
    if 'tone' in lowered or 'formal' in lowered or 'casual' in lowered:
        preference_notes.append('has explicit tone preferences that should be saved to memory')

    summary = {
        'status': 'ok',
        'run_dir': str(run_dir),
        'detected_categories': record['detected_categories'],
        'preference_notes_for_memory': preference_notes,
        'heuristics_file': str(HEURISTICS_FILE),
        'prompt_update_proposals': str(PROMPT_UPDATE_PROPOSALS) if PROMPT_UPDATE_PROPOSALS.exists() else '',
    }
    print(json.dumps(summary, indent=2))
    return 0


def show_review_last() -> int:
    run_dir = latest_run_dir()
    if not run_dir:
        print('No latest run found.')
        return 1
    path = run_dir / 'review_summary.md'
    if not path.exists():
        print('No review_summary.md found for the latest run.')
        return 1
    print(read_text(path))
    return 0


def show_article_last() -> int:
    run_dir = latest_run_dir()
    if not run_dir:
        print('No latest run found.')
        return 1
    path = run_dir / 'article.tex'
    if not path.exists():
        print('No article.tex found for the latest run.')
        return 1
    content = read_text(path)
    preview = '\n'.join(content.splitlines()[:80])
    print(f'Path: {path}\n')
    print(preview)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Research article pipeline orchestrator')
    sub = parser.add_subparsers(dest='command', required=True)

    run = sub.add_parser('run')
    run.add_argument('--topic', required=True)
    run.add_argument('--hypothesis', required=True)
    run.add_argument('--title', required=True)
    run.add_argument('--tone', default='analytical')
    run.add_argument('--audience', default='educated general reader')
    run.add_argument('--length', default='publication-ready manuscript draft')
    run.add_argument('--max-iterations', type=int, default=2)
    run.add_argument('--compile-pdf', action='store_true', help='Compile article.tex into article.pdf locally on this machine')
    run.add_argument('--skip-overleaf-compile', action='store_true', help='Do not attempt remote Overleaf compilation via olcli when local compilation is disabled')
    run.add_argument('--skip-github-push', action='store_true', help='Do not push generated artifacts to GitHub after the run completes')
    run.add_argument('--skip-publishing-hub', action='store_true', help='Do not update the publishing-hub repository/site after the run completes')
    run.add_argument('--skip-netlify-deploy', action='store_true', help='Update the publishing-hub repository but skip Netlify deployment even if credentials are configured')

    feedback = sub.add_parser('feedback')
    feedback.add_argument('--message', required=True)
    feedback.add_argument('--run-dir', default='')

    sub.add_parser('reviewlast')
    sub.add_parser('articlelast')
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == 'run':
        return run_pipeline(args)
    if args.command == 'feedback':
        return handle_feedback(args)
    if args.command == 'reviewlast':
        return show_review_last()
    if args.command == 'articlelast':
        return show_article_last()
    parser.print_help()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
