import html
import random
import re
import time
from urllib.parse import urljoin

import requests

from .job_record import build_record_fields
from .keyword_catalog import extract_keywords

BASE_URL = "https://www.saramin.co.kr"
SEARCH_URL = (
    f"{BASE_URL}/zf_user/jobs/list/job-category"
    "?cat_mcls=2&panel_type=&search_optional_item=n&search_done=y"
    "&panel_count=y&preview=y&page_count=50&sort=RL"
)
CACHE_SCOPE = "saramin:job-category:cat-mcls-2:all-it:v4"
MAX_WORKERS = 1
MAX_LIST_PAGES = 100
LIST_DELAY_RANGE = (6.0, 10.0)
DETAIL_DELAY_RANGE = (4.0, 8.0)
BLOCK_COOLDOWN_SECONDS = 30 * 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

BLOCK_TEXT_PAT = re.compile(r"(captcha|보안문자|비정상|자동\s*접속|접근이\s*제한)", re.IGNORECASE)
EXPERIENCE_PATTERNS = (
    re.compile(r"경력\s*무관"),
    re.compile(r"신입"),
    re.compile(r"경력\s*(\d+)\s*년\s*(?:이상|↑|~)"),
    re.compile(r"(\d+)\s*년\s*(?:이상|↑)"),
    re.compile(r"(\d+)\s*년\s*[~\-]\s*(\d+)\s*년"),
)


_blocked_until = 0.0


def _traffic_pause(delay_range: tuple[float, float]):
    """연속 요청을 피하기 위해 지정 범위 안에서 충분히 대기한다."""
    remaining = _blocked_until - time.monotonic()
    if remaining > 0:
        minutes = max(1, int(remaining / 60) + 1)
        raise RuntimeError(f"사람인 접근 제한 대기 중입니다. 약 {minutes}분 후 다시 시도하세요.")
    time.sleep(random.uniform(*delay_range))


def _absolute_url(url: str) -> str:
    return urljoin(BASE_URL, url)


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _html_text(source: str) -> str:
    return _normalize_space(html.unescape(re.sub(r"<[^>]+>", " ", source or "")))


def _attribute(tag: str, name: str) -> str:
    match = re.search(rf'\b{re.escape(name)}="([^"]*)"', tag, re.IGNORECASE)
    return html.unescape(html.unescape(match.group(1))) if match else ""


def _parse_experience(text: str) -> tuple[int, int]:
    text = _normalize_space(text)
    if not text:
        return 0, 10
    if EXPERIENCE_PATTERNS[0].search(text):
        return 0, 10
    if "신입" in text and "경력" in text:
        return 0, 10
    if EXPERIENCE_PATTERNS[1].search(text):
        return 0, 0

    range_match = EXPERIENCE_PATTERNS[4].search(text)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))

    for pat in EXPERIENCE_PATTERNS[2:4]:
        match = pat.search(text)
        if match:
            return int(match.group(1)), 10

    return 0, 10


def _raise_if_blocked(text: str):
    global _blocked_until
    if BLOCK_TEXT_PAT.search(text):
        _blocked_until = time.monotonic() + BLOCK_COOLDOWN_SECONDS
        raise RuntimeError("사람인 접근 제한 또는 보안 확인 화면이 감지되어 수집을 중단했습니다.")


def _fetch_list_page(page_no: int) -> str:
    url = f"{SEARCH_URL}&page={page_no}"
    for attempt in range(3):
        _traffic_pause(LIST_DELAY_RANGE if attempt == 0 else (20.0, 40.0))
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            if response.status_code == 429:
                time.sleep(60 * (attempt + 1))
                continue
            response.raise_for_status()
            _raise_if_blocked(response.text)
            return response.text
        except requests.RequestException:
            if attempt == 2:
                raise
    return ""


def _parse_list_page(source: str) -> list[dict]:
    """서버 렌더링 목록 HTML에서 공고 메타데이터를 추출한다."""
    starts = list(re.finditer(r'<div id="rec-(\d+)" class="list_item[^\"]*">', source))
    jobs = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(source)
        block = source[start.start():end]
        job_id = int(start.group(1))
        anchor_match = re.search(
            rf'<a\b[^>]*\bid="rec_link_{job_id}"[^>]*>',
            block,
            re.IGNORECASE,
        )
        if not anchor_match:
            continue
        anchor = anchor_match.group(0)
        title = _normalize_space(_attribute(anchor, "title"))
        href = _attribute(anchor, "href")
        company_match = re.search(
            r'class="col company_nm".*?<a\b[^>]*>(.*?)</a>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        career_match = re.search(
            r'class="career"[^>]*>(.*?)</p>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        location_match = re.search(
            r'class="work_place"[^>]*>(.*?)</p>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        sector_match = re.search(
            r'class="job_sector"[^>]*>(.*?)</span>\s*</div>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        deadline_match = re.search(
            r'class="support_detail".*?class="date"[^>]*>(.*?)</span>',
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if title and href:
            jobs.append({
                "id": job_id,
                "href": href,
                "title": title,
                "company": _html_text(company_match.group(1)) if company_match else "",
                "career": _html_text(career_match.group(1)) if career_match else "",
                "location": _html_text(location_match.group(1)) if location_match else "",
                "sectors": _html_text(sector_match.group(1)) if sector_match else "",
                "deadline": _html_text(deadline_match.group(1)) if deadline_match else "",
            })
    return jobs


def collect_all_jobs(progress_cb=None) -> list[dict]:
    """사람인 IT개발·데이터 목록 전체 공고를 수집한다."""
    seen: set[int] = set()
    jobs: list[dict] = []
    for page_no in range(1, MAX_LIST_PAGES + 1):
        found = _parse_list_page(_fetch_list_page(page_no))
        if not found:
            break
        before = len(jobs)
        for item in found:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            annual_from, annual_to = _parse_experience(item["career"])
            jobs.append({
                "id": item["id"],
                "title": item["title"],
                "company": item["company"],
                "location": item["location"],
                "annual_from": annual_from,
                "annual_to": annual_to,
                "url": _absolute_url(item["href"]),
                "sectors": item["sectors"],
                "deadline": item["deadline"],
            })
        if progress_cb and len(jobs) != before:
            progress_cb(len(jobs))
    return jobs


def _detail_text_from_html(source: str) -> str:
    source = re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<br\s*/?>|</(?:p|div|li|tr|td|th|h[1-6])>", "\n", source, flags=re.I)
    source = re.sub(r"<[^>]+>", " ", source)
    lines = [
        _normalize_space(html.unescape(html.unescape(line)))
        for line in source.splitlines()
    ]
    return "\n".join(line for line in lines if line)


def _fetch_detail(job_meta: dict) -> str:
    detail_url = (
        f"{BASE_URL}/zf_user/jobs/relay/view-detail"
        f"?rec_idx={job_meta['id']}&rec_seq=0"
        "&t_category=non-logged_relay_view&t_content=view_detail"
    )
    headers = {**HEADERS, "Referer": job_meta["url"]}
    for attempt in range(3):
        _traffic_pause(DETAIL_DELAY_RANGE if attempt == 0 else (20.0, 40.0))
        try:
            response = requests.get(detail_url, headers=headers, timeout=30)
            if response.status_code == 429:
                time.sleep(60 * (attempt + 1))
                continue
            response.raise_for_status()
            _raise_if_blocked(response.text)
            return _detail_text_from_html(response.text)
        except requests.RequestException:
            if attempt == 2:
                raise
    return ""


def extract_langs(text: str) -> list[str]:
    return extract_keywords(text)


def process_job(job_meta: dict) -> dict:
    """사람인 상세 페이지에서 본문을 읽고 기술스택과 경력 정보를 보강한다."""
    detail_text = _fetch_detail(job_meta)
    title = job_meta.get("title", "제목 없음")
    company = job_meta.get("company", "")
    annual_from = job_meta.get("annual_from", 0)
    annual_to = job_meta.get("annual_to", 10)
    full_text = " ".join([title, company, detail_text])
    record_fields = build_record_fields(
        title=title,
        content=detail_text,
        hints=job_meta.get("sectors", ""),
        deadline=job_meta.get("deadline"),
    )

    return {
        "title": title,
        "company": company,
        "annual_from": annual_from,
        "annual_to": annual_to,
        "langs": extract_langs(full_text),
        **record_fields,
        "_detail_markdown": "## 공고 내용\n\n" + detail_text,
    }
