import html
import re
import time
import threading

import requests
from playwright.sync_api import sync_playwright

from .keyword_catalog import INCLUDE_TITLE_KEYWORDS, extract_keywords

BASE_URL = "https://www.wanted.co.kr/api/v4/jobs"
LIST_URL = (
    "https://www.wanted.co.kr/wdlist/518"
    "?country=kr&job_sort=job.latest_order&years=-1&locations=all"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.wanted.co.kr/wdlist/518?country=kr&job_sort=job.latest_order&years=-1&locations=all",
    "Origin": "https://www.wanted.co.kr",
    "x-wanted-platform": "pcweb",
}

CATEGORY = 518

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
        get_session().get(
            "https://www.wanted.co.kr/wdlist/518?country=kr&job_sort=job.latest_order&years=-1&locations=all",
            timeout=10,
        )
    except requests.RequestException:
        pass


def fetch_job_list(offset: int, limit: int = 100) -> dict:
    params = {
        "job_sort":  "job.latest_order",
        "years":     -1,
        "country":   "kr",
        "locations": "all",
        "category":  CATEGORY,
        "limit":     limit,
        "offset":    offset,
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


def collect_all_jobs(progress_cb=None) -> list[dict]:
    """Playwright로 /wdlist/518 스크롤 수집 → 키워드 매칭 공고 (id, title) 반환.
    프로모션/추천 공고까지 포함. annual_from/to는 상세 API에서 채워짐(process_job)."""
    pairs = _scrape_list_pairs(progress_cb)
    seen: set[int] = set()
    jobs: list[dict] = []
    for jid, title in pairs:
        if jid in seen:
            continue
        seen.add(jid)
        if INCLUDE_TITLE_KEYWORDS.search(title):
            jobs.append({"id": jid, "title": title})
    return jobs


def _scrape_list_pairs(progress_cb=None) -> list[tuple[int, str]]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[data-cy="job-card"]', timeout=15000)

        prev_count = 0
        stable = 0
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            count = page.locator('[data-cy="job-card"]').count()
            if progress_cb and count != prev_count:
                progress_cb(count)
            if count == prev_count:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            prev_count = count

        raw = page.evaluate(r"""
            () => {
                const out = [];
                document.querySelectorAll('[data-cy="job-card"]').forEach(card => {
                    const btn = card.querySelector('button[data-position-name]');
                    const a = card.querySelector('a[href*="/wd/"]');
                    if (!btn || !a) return;
                    const title = btn.getAttribute('data-position-name');
                    const m = a.getAttribute('href').match(/\/wd\/(\d+)/);
                    if (title && m) out.push([parseInt(m[1], 10), title]);
                });
                return out;
            }
        """)
        browser.close()
    return [(int(jid), t) for jid, t in raw]


def extract_langs(detail_data: dict) -> list[str]:
    """공고 상세에서 감지된 언어/기술 목록 반환"""
    job = detail_data.get("job", {})
    parts = [job.get("position") or job.get("title", "")]

    for tag in job.get("tags", []):
        parts.append(tag.get("title", ""))

    detail = job.get("detail", {})
    for field in ("intro", "main_tasks", "requirements", "benefits"):
        text = detail.get(field, "") or ""
        text = re.sub(r"<[^>]+>", " ", text)
        parts.append(text)

    full_text = " ".join(parts)
    return extract_keywords(full_text)


def _clean_detail_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.IGNORECASE)
    value = re.sub(r"</(?:p|div|li|h[1-6])>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", " ", value)
    lines = [re.sub(r"\s+", " ", line).strip() for line in html.unescape(value).splitlines()]
    return "\n".join(line for line in lines if line)


def _wanted_detail_markdown(job: dict) -> str:
    detail = job.get("detail") or {}
    sections = (
        ("회사 소개", "intro"),
        ("주요 업무", "main_tasks"),
        ("자격 요건", "requirements"),
        ("우대 사항", "preferred_points"),
        ("혜택 및 복지", "benefits"),
    )
    output: list[str] = []
    for heading, field in sections:
        text = _clean_detail_text(detail.get(field, ""))
        if text:
            output.extend([f"## {heading}", "", text, ""])
    return "\n".join(output).strip()


def process_job(job_id: int) -> dict:
    """공고 상세를 가져와 langs, annual_from, annual_to 반환.
    리스트는 Playwright라 연차 정보가 없어 여기서 상세 API로 채운다."""
    detail = fetch_job_detail(job_id)
    job = detail.get("job", {})
    company = job.get("company") or {}
    address = job.get("address") or {}
    annual_from = job.get("annual_from") or 0
    annual_to = job.get("annual_to")
    if annual_to is None or annual_to < 0:
        annual_to = 10
    return {
        "title":       job.get("position") or job.get("title") or "제목 없음",
        "company":     company.get("name", ""),
        "location":    address.get("full_location") or address.get("location", ""),
        "url":         f"https://www.wanted.co.kr/wd/{job_id}",
        "langs":       extract_langs(detail),
        "annual_from": annual_from,
        "annual_to":   annual_to,
        "_detail_markdown": _wanted_detail_markdown(job),
    }

