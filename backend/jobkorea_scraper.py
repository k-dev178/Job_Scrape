import html
import re
import threading
import time

import requests

from .job_record import build_record_fields
from .keyword_catalog import extract_keywords

BASE_URL = "https://www.jobkorea.co.kr"
SEARCH_API_URL = f"{BASE_URL}/Search/api/display/v2/jobs"
IT_JOB_CODES = (
    "1000229", "1000230", "1000231", "1000232", "1000233", "1000234",
    "1000235", "1000236", "1000237", "1000238", "1000239", "1000240",
    "1000241", "1000242", "1000243", "1000244", "1000245", "1000246",
    "1000247", "1000417", "1000418", "1000419", "1000420", "1000421",
    "1000422", "1000423",
)
CACHE_SCOPE = "jobkorea:nationwide:ai-development-data:all-it:v2"
PAGE_SIZE = 100
MAX_WORKERS = 1
REQUEST_INTERVAL_SECONDS = 4.0
BLOCK_COOLDOWN_SECONDS = 30 * 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": f"{BASE_URL}/Search?duty={','.join(IT_JOB_CODES)}",
}

_local = threading.local()
_request_lock = threading.Lock()
_cooldown_lock = threading.Lock()
_last_request_at = 0.0
_blocked_until = 0.0

BLOCK_TEXT_PAT = re.compile(
    r"(captcha|보안문자|보안\s*정책|비정상\s*접근|자동\s*접속|"
    r"접근이\s*제한|접속이\s*일시적으로\s*제한)",
    re.IGNORECASE,
)


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _normalize_company(text: str) -> str:
    return re.sub(r"\s*관심기업\s*$", "", _normalize_space(text))


def _parse_experience(text: str) -> tuple[int, int]:
    """잡코리아 경력 표기를 웹의 0~10년 범위 모델로 변환한다."""
    text = _normalize_space(text)
    if not text or "경력무관" in text:
        return 0, 10
    if "신입" in text and "경력" in text:
        return 0, 10
    if "신입" in text:
        return 0, 0

    range_match = re.search(r"(\d+)\s*년\s*[~\-]\s*(\d+)\s*년", text)
    if range_match:
        return int(range_match.group(1)), min(int(range_match.group(2)), 10)

    maximum_match = re.search(r"(\d+)\s*년\s*이하", text)
    if maximum_match:
        return 0, min(int(maximum_match.group(1)), 10)

    minimum_match = re.search(r"(?:경력\s*)?(\d+)\s*년\s*(?:이상|↑)", text)
    if minimum_match:
        return min(int(minimum_match.group(1)), 10), 10

    return 0, 10


def _raise_if_blocked(text: str):
    global _blocked_until
    if BLOCK_TEXT_PAT.search(text):
        with _cooldown_lock:
            _blocked_until = time.monotonic() + BLOCK_COOLDOWN_SECONDS
        raise RuntimeError("잡코리아 접근 제한 또는 보안 확인 화면이 감지되었습니다.")


def _wait_for_request_slot():
    """잡코리아 요청을 직렬화하고 요청 사이에 충분한 간격을 둔다."""
    global _last_request_at
    with _request_lock:
        with _cooldown_lock:
            cooldown_remaining = _blocked_until - time.monotonic()
        if cooldown_remaining > 0:
            minutes = max(1, int(cooldown_remaining / 60) + 1)
            raise RuntimeError(
                f"잡코리아 보안 차단 대기 중입니다. 약 {minutes}분 후 다시 시도하세요."
            )
        wait_seconds = REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        _last_request_at = time.monotonic()


def _get_session() -> requests.Session:
    if not hasattr(_local, "session"):
        session = requests.Session()
        session.headers.update(HEADERS)
        _local.session = session
    return _local.session


def _retry_delay(response: requests.Response, attempt: int) -> int:
    try:
        return max(30, int(response.headers.get("Retry-After", "")))
    except ValueError:
        return 30 * (attempt + 1)


def _search_payload(page: int) -> dict:
    return {
        "pageSize": PAGE_SIZE,
        "page": page,
        "sortProperty": "2",
        "sortDirection": "DESC",
        "keyword": "",
        "jobClassificationCodeList": list(IT_JOB_CODES),
        "jobClassificationSubCodeList": [],
        "industryCodeList": [],
        "industrySubCodeList": [],
        "locationList": [],
        "careerList": [],
        "careerMin": "",
        "careerMax": "",
        "companyTypeList": [],
        "educationCodeList": [],
        "employmentTypeList": [],
        "excludeKeywordList": [],
        "designationCodeList": [],
        "filterList": [],
        "benefitCodeList": [],
        "payType": "",
        "payMin": 0,
        "payMax": 0,
        "onePick": "",
        "period": "",
        "featureType": "",
        "deviceType": "PC",
    }


def _fetch_job_page(page: int) -> dict:
    for attempt in range(3):
        try:
            _wait_for_request_slot()
            response = _get_session().post(
                SEARCH_API_URL,
                json=_search_payload(page),
                timeout=20,
            )
            if response.status_code == 429:
                time.sleep(_retry_delay(response, attempt))
                continue
            response.raise_for_status()
            _raise_if_blocked(response.text)
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    return {}


def _experience_from_api(item: dict) -> tuple[int, int]:
    career_type = str(item.get("careerType") or "")
    career_range = min(int(item.get("careerRange") or 0), 10)
    if career_type == "1":
        return 0, 0
    if career_type == "2":
        return career_range, 10
    return 0, 10


def collect_all_jobs(progress_cb=None) -> list[dict]:
    """전국 AI·개발·데이터 직군 공고를 검색 API의 모든 페이지에서 수집한다."""
    first_page = _fetch_job_page(0)
    total_pages = int(first_page.get("totalPages") or 0)
    seen: set[int] = set()
    jobs: list[dict] = []

    def append_page(page_data: dict):
        for item in page_data.get("content", []):
            job_id = int(item["id"])
            if job_id in seen:
                continue
            seen.add(job_id)
            annual_from, annual_to = _experience_from_api(item)
            application_period = item.get("applicationPeriod") or {}
            jobs.append({
                "id": job_id,
                "title": _normalize_space(item.get("title", "")) or "제목 없음",
                "company": _normalize_company(
                    item.get("companyName") or item.get("postingCompanyName") or ""
                ),
                "annual_from": annual_from,
                "annual_to": annual_to,
                "url": f"{BASE_URL}/Recruit/GI_Read/{job_id}",
                "keywords": item.get("_internal_keywordList") or [],
                "sectors": item.get("jobClassificationOrIndustry") or "",
                "deadline": (
                    application_period.get("end")
                    or item.get("deadline")
                    or item.get("endDate")
                    or item.get("applicationEndDate")
                    or item.get("endDt")
                    or ""
                ),
            })
        if progress_cb:
            progress_cb(len(jobs))

    append_page(first_page)
    for page in range(1, total_pages):
        append_page(_fetch_job_page(page))
    return jobs


def extract_langs(text: str) -> list[str]:
    return extract_keywords(text)


def _detail_text_from_html(source: str) -> str:
    start = source.find('id="details-section"')
    end = source.find('id="company-section"', start + 1)
    if start >= 0:
        source = source[start:end if end >= 0 else None]
    source = re.sub(r"<script\b[^>]*>.*?</script>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<style\b[^>]*>.*?</style>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<br\s*/?>|</(?:p|div|li|h[1-6])>", "\n", source, flags=re.I)
    source = re.sub(r"<[^>]+>", " ", source)
    lines = [
        _normalize_space(line)
        for line in html.unescape(source).splitlines()
    ]
    return "\n".join(line for line in lines if line)


def _fetch_detail_text(url: str) -> str:
    for attempt in range(3):
        try:
            _wait_for_request_slot()
            response = _get_session().get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                },
                timeout=20,
            )
            if response.status_code == 429:
                time.sleep(_retry_delay(response, attempt))
                continue
            response.raise_for_status()
            _raise_if_blocked(response.text)
            return _detail_text_from_html(response.text)
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    return ""


def process_job(job_meta: dict) -> dict:
    """상세 공고의 본문에서 회사, 경력, 기술스택을 추출한다."""
    title = job_meta.get("title", "제목 없음")
    company = job_meta.get("company", "")
    keyword_text = " ".join(job_meta.get("keywords", []))
    sector_text = str(job_meta.get("sectors") or "")
    try:
        detail_text = _fetch_detail_text(job_meta["url"])
    except requests.RequestException:
        detail_text = ""

    annual_from = job_meta.get("annual_from", 0)
    annual_to = job_meta.get("annual_to", 10)
    if detail_text:
        parsed_from, parsed_to = _parse_experience(detail_text)
        if (parsed_from, parsed_to) != (0, 10):
            annual_from, annual_to = parsed_from, parsed_to

    full_text = " ".join([title, company, keyword_text, sector_text, detail_text])
    record_fields = build_record_fields(
        title=title,
        content=detail_text,
        hints=f"{keyword_text} {sector_text}",
        deadline=job_meta.get("deadline"),
    )
    return {
        "title": title,
        "company": company,
        "annual_from": annual_from,
        "annual_to": annual_to,
        "langs": extract_langs(full_text),
        **record_fields,
        "_detail_markdown": (
            f"## 공고 내용\n\n{detail_text}"
            if detail_text
            else ""
        ),
    }
