import re
import time
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE_URL = "https://www.wanted.co.kr/api/v4/jobs"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.wanted.co.kr/wdlist/518",
    "Origin": "https://www.wanted.co.kr",
    "x-wanted-platform": "pcweb",
}

BACKEND_CATEGORY = 518

LANGUAGES = {
    "Python":     r"\bpython\b",
    "Java":       r"\bjava\b(?!script)",
    "Kotlin":     r"\bkotlin\b",
    "Go":         r"\b(go|golang)\b",
    "Node.js":    r"\bnode\.?js\b",
    "JavaScript": r"\b(javascript|js)\b",
    "TypeScript": r"\b(typescript|ts)\b",
    "C++":        r"\bc\+\+\b",
    "C#":         r"\bc#\b",
    "Ruby":       r"\bruby\b",
    "PHP":        r"\bphp\b",
    "Scala":      r"\bscala\b",
    "Rust":       r"\brust\b",
    "Swift":      r"\bswift\b",
    "Spring":     r"\bspring(\s*boot)?\b",
    "Django":     r"\bdjango\b",
    "FastAPI":    r"\bfastapi\b",
    "Flask":      r"\bflask\b",
    "Rails":      r"\b(rails|ruby on rails)\b",
    "NestJS":     r"\bnest\.?js\b",
    "Express":    r"\bexpress\.?js\b",
    "Laravel":    r"\blaravel\b",
    "MySQL":      r"\bmysql\b",
    "PostgreSQL": r"\b(postgresql|postgres)\b",
    "MongoDB":    r"\bmongodb\b",
    "Redis":      r"\bredis\b",
    "Docker":     r"\bdocker\b",
    "Kubernetes": r"\b(kubernetes|k8s)\b",
    "AWS":        r"\baws\b",
}

COMPILED = {lang: re.compile(pat, re.IGNORECASE) for lang, pat in LANGUAGES.items()}

EXCLUDE_TITLE_KEYWORDS = re.compile(
    r"데이터\s*(엔지니어|사이언티스트|분석|플랫폼|파이프라인|리드|팀장|아키텍트)"
    r"|data\s*(engineer|scientist|analyst|platform|pipeline)"
    r"|머신\s*러닝|machine\s*learning|딥\s*러닝|deep\s*learning"
    r"|\bML\b|\bMLOps\b|\bMLops\b"
    r"|\bAI\s*(엔지니어|개발|리서처|연구|플랫폼)"
    r"|인공\s*지능"
    r"|플랫폼\s*(엔지니어|개발자|팀)"
    r"|인프라\s*(엔지니어|개발자|팀)"
    r"|DevOps|SRE|클라우드\s*(엔지니어|아키텍트)"
    r"|빅\s*데이터",
    re.IGNORECASE,
)

MAX_WORKERS = 10

_local = threading.local()


def get_session() -> requests.Session:
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers.update(HEADERS)
        _local.session = s
    return _local.session


def init_session():
    try:
        get_session().get("https://www.wanted.co.kr/wdlist/518", timeout=10)
    except requests.RequestException:
        pass


def fetch_job_list(offset: int, limit: int = 100) -> dict:
    params = {
        "job_sort": "job.latest_order",
        "years": -1,
        "country": "kr",
        "locations": "all",
        "category": BACKEND_CATEGORY,
        "limit": limit,
        "offset": offset,
    }
    for attempt in range(3):
        try:
            resp = get_session().get(BASE_URL, params=params, timeout=10)
            if resp.status_code == 429:
                time.sleep(5)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2)
    return {}


def fetch_job_detail(job_id: int) -> dict:
    url = f"{BASE_URL}/{job_id}"
    for attempt in range(2):
        try:
            resp = get_session().get(url, timeout=10)
            if resp.status_code == 429:
                time.sleep(5)
                continue
            if resp.status_code != 200:
                return {}
            return resp.json()
        except requests.RequestException:
            time.sleep(1)
    return {}


def collect_all_job_ids() -> list[int]:
    job_ids = []
    offset = 0
    limit = 100

    while True:
        data = fetch_job_list(offset, limit)
        jobs = data.get("data", [])
        if not jobs:
            break
        for job in jobs:
            jid = job.get("id")
            if jid:
                job_ids.append(jid)
        has_next = bool(data.get("links", {}).get("next"))
        if not has_next:
            break
        offset += limit
        time.sleep(0.2)

    return job_ids


def extract_text_from_job(detail_data: dict) -> tuple[str, str]:
    job = detail_data.get("job", {})
    title = job.get("title", "")
    parts = [title]
    for tag in job.get("tags", []):
        parts.append(tag.get("title", ""))
    detail = job.get("detail", {})
    for field in ("intro", "main_tasks", "requirements", "preferred_points", "benefits"):
        text = detail.get(field, "") or ""
        text = re.sub(r"<[^>]+>", " ", text)
        parts.append(text)
    return title, " ".join(parts)


def is_backend_job(title: str) -> bool:
    return not EXCLUDE_TITLE_KEYWORDS.search(title)


def process_job(job_id: int) -> tuple[str, str]:
    detail = fetch_job_detail(job_id)
    return extract_text_from_job(detail)


def count_languages(texts: list[str]) -> dict[str, int]:
    counts = defaultdict(int)
    for text in texts:
        for lang, pattern in COMPILED.items():
            if pattern.search(text):
                counts[lang] += 1
    return counts
