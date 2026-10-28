"""Bounded web searches. Results are search snippets, not full-page verification."""
import asyncio
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit


def parse_queries(content, question):
    try:
        start, end = content.index('['), content.rindex(']') + 1
        values = json.loads(content[start:end])
        if not isinstance(values, list):
            raise ValueError('Expected query list')
        queries = list(dict.fromkeys(q.strip()[:160] for q in values if isinstance(q, str) and q.strip()))[:3]
    except (ValueError, TypeError):
        queries = []
    return queries or [question.strip()[:160]]


def normalize_results(rows):
    results, seen = [], set()
    for row in rows:
        url = str(row.get('href') or row.get('url') or '').strip()
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username:
                continue
        except ValueError:
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append({'id': len(results) + 1, 'title': str(row.get('title') or parsed.hostname)[:180],
                        'url': url, 'snippet': str(row.get('body') or row.get('snippet') or '')[:700]})
        if len(results) == 6:
            break
    return results


def _search(queries):
    from ddgs import DDGS
    rows = []
    errors = []
    engine = DDGS(timeout=12)
    for query in queries:
        try:
            rows.extend(engine.text(query, max_results=3, backend='bing,duckduckgo', region='wt-wt'))
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {str(exc)[:120]}')
    results = normalize_results(rows)
    if not results:
        raise ValueError('搜索服务没有返回可用结果，可能被限流或网络不可达。' + (' ' + errors[0] if errors else ''))
    return results


async def search_web(queries):
    return await asyncio.wait_for(asyncio.to_thread(_search, queries), timeout=45)


def evidence_text(queries, sources):
    return json.dumps({'retrieved_at': datetime.now(timezone.utc).isoformat(), 'queries': queries,
                       'scope': '仅搜索结果摘要，未读取网页全文；检索时间不等于文章发布日期。',
                       'sources': sources}, ensure_ascii=False)
