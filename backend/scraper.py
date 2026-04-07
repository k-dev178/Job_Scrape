import re
import time
import threading
from collections import defaultdict

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

CATEGORY    = 518
TAG_TYPE_ID = 872

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

# 제목에 아래 키워드가 있는 공고만 분석 (화이트리스트)
INCLUDE_TITLE_KEYWORDS = re.compile(
    r"백엔드|백 엔드|[Bb]ack.?[Ee]nd|서버|[Ss]erver",
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
    """메인 페이지를 먼저 방문해 쿠키 획득"""
    try:
        get_session().get("https://www.wanted.co.kr/wdlist/518", timeout=10)
    except requests.RequestException:
        pass


def fetch_job_list(offset: int, limit: int = 100) -> dict:
    params = {
        "job_sort":     "job.latest_order",
        "years":        -1,
        "country":      "kr",
        "locations":    "all",
        "category":     CATEGORY,
        "tag_type_ids": TAG_TYPE_ID,
        "limit":        limit,
        "offset":       offset,
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


def collect_all_jobs() -> list[dict]:
    """백엔드/서버 키워드 공고 전체 수집 (annual_from, annual_to 포함)"""
    jobs = []
    offset = 0
    limit = 100

    while True:
        data = fetch_job_list(offset, limit)
        items = data.get("data", [])
        if not items:
            break

        for item in items:
            title = item.get("position", "")
            if INCLUDE_TITLE_KEYWORDS.search(title):
                jid = item.get("id")
                if jid:
                    annual_from = item.get("annual_from") or 0
                    annual_to   = item.get("annual_to")
                    # None이나 -1이면 상한 없음 → 10으로 처리
                    if annual_to is None or annual_to < 0:
                        annual_to = 10
                    jobs.append({
                        "id":           jid,
                        "annual_from":  annual_from,
                        "annual_to":    annual_to,
                    })

        has_next = bool(data.get("links", {}).get("next"))
        if not has_next:
            break

        offset += limit
        time.sleep(0.2)

    return jobs


def extract_langs(detail_data: dict) -> list[str]:
    """공고 상세에서 감지된 언어/기술 목록 반환"""
    job = detail_data.get("job", {})
    parts = [job.get("title", "")]

    for tag in job.get("tags", []):
        parts.append(tag.get("title", ""))

    detail = job.get("detail", {})
    for field in ("intro", "main_tasks", "requirements", "preferred_points", "benefits"):
        text = detail.get(field, "") or ""
        text = re.sub(r"<[^>]+>", " ", text)
        parts.append(text)

    full_text = " ".join(parts)
    return [lang for lang, pat in COMPILED.items() if pat.search(full_text)]


def process_job(job_id: int) -> list[str]:
    """공고 상세를 가져와 감지된 언어 목록 반환"""
    detail = fetch_job_detail(job_id)
    return extract_langs(detail)


def aggregate_results(jobs: list[dict],
                      years_min: int = 0,
                      years_max: int = 10) -> tuple[list[dict], int]:
    """경력 범위로 jobs 필터링 후 언어 카운트 집계.
    반환: (results 리스트, 분석 공고 수)"""
    filtered = [
        j for j in jobs
        if j["annual_from"] <= years_max and j["annual_to"] >= years_min
    ]

    counts: dict[str, int] = defaultdict(int)
    for job in filtered:
        for lang in job.get("langs", []):
            counts[lang] += 1

    results = [
        {
            "rank":  i + 1,
            "lang":  lang,
            "count": cnt,
            "ratio": round(cnt / len(filtered) * 100, 1) if filtered else 0,
        }
        for i, (lang, cnt) in enumerate(sorted(counts.items(), key=lambda x: x[1], reverse=True))
    ]
    return results, len(filtered)
