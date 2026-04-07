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

# 백엔드 카테고리 ID
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

# 제목에 이 키워드가 포함되면 제외 (데이터/AI/인프라 직군)
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
    """메인 페이지를 먼저 방문해 쿠키 획득"""
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
        except requests.RequestException as e:
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
    """전체 백엔드 공고 ID 수집"""
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

        fetched = len(job_ids)
        has_next = bool(data.get("links", {}).get("next"))
        print(f"  목록 수집 중: {fetched}개", end="\r", flush=True)

        if not has_next:
            break

        offset += limit
        time.sleep(0.2)

    print(f"  목록 수집 완료: {len(job_ids)}개          ")
    return job_ids


def extract_text_from_job(detail_data: dict) -> tuple[str, str]:
    """공고 상세에서 (제목, 전체텍스트) 반환"""
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
    """데이터/AI/인프라 직군 제외"""
    return not EXCLUDE_TITLE_KEYWORDS.search(title)


def process_job(job_id: int) -> tuple[str, str]:
    detail = fetch_job_detail(job_id)
    return extract_text_from_job(detail)


def count_languages(texts: list[str]) -> dict[str, int]:
    """각 공고당 언급된 언어를 카운트 (공고 수 기준)"""
    counts = defaultdict(int)
    for text in texts:
        for lang, pattern in COMPILED.items():
            if pattern.search(text):
                counts[lang] += 1
    return counts


def print_results(counts: dict[str, int], total: int):
    print()
    print("=" * 52)
    print("   원티드 백엔드 공고 언어/기술스택 분석 결과")
    print("=" * 52)
    print(f"   총 분석 공고 수: {total:,}개")
    print("=" * 52)
    print(f"{'순위':>4}  {'언어/기술':<14}  {'언급 공고수':>10}  {'비율':>6}")
    print("-" * 44)

    sorted_items = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    for rank, (lang, count) in enumerate(sorted_items, 1):
        ratio = count / total * 100 if total else 0
        print(f"{rank:>4}  {lang:<14}  {count:>10,}  {ratio:>5.1f}%")

    print("=" * 52)


def main():
    print("원티드 백엔드 공고 스크래퍼 시작\n")

    print("세션 초기화 중...")
    init_session()

    print("[1/2] 공고 목록 수집 중...")
    job_ids = collect_all_job_ids()

    if not job_ids:
        print("공고를 가져오지 못했습니다. 네트워크 또는 API 상태를 확인하세요.")
        sys.exit(1)

    print(f"\n[2/2] 공고 상세 분석 중 (총 {len(job_ids):,}개, 병렬 {MAX_WORKERS}개)...")
    texts = []
    skipped_titles = []
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_job, jid): jid for jid in job_ids}
        for future in as_completed(futures):
            title, text = future.result()
            done += 1
            if not is_backend_job(title):
                skipped_titles.append(title)
            elif text.strip():
                texts.append(text)
            if done % 50 == 0 or done == len(job_ids):
                print(f"  분석 중: {done}/{len(job_ids)} (필터 제외: {len(skipped_titles)}개)", end="\r", flush=True)

    print(f"  분석 완료: {len(texts)}개 (데이터/AI/인프라 {len(skipped_titles)}개 제외)          ")
    if skipped_titles:
        print("\n[제외된 공고 샘플 (최대 10개)]")
        for t in skipped_titles[:10]:
            print(f"  - {t}")

    counts = count_languages(texts)
    print_results(counts, len(texts))


if __name__ == "__main__":
    main()
