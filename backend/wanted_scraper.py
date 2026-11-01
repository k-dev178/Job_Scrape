import html
import re
from .job_record import build_record_fields, is_expired, matches_backend_role
from .keyword_catalog import extract_job_keywords
from .scrape_http import JobDetailUnavailable, JsonClient, SourceUnavailable

BASE_URL = "https://www.wanted.co.kr/api/v4/jobs"
LIST_URL = (
    "https://www.wanted.co.kr/wdlist/518/872"
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
    "Referer": LIST_URL,
    "Origin": "https://www.wanted.co.kr",
    "x-wanted-platform": "pcweb",
}

CATEGORY = 872  # 원티드의 '서버 개발자' 직무
CACHE_SCOPE = "wanted:role-872:web-backend:v3"

MAX_WORKERS = 1
_client = JsonClient("Wanted", HEADERS)

def init_session():
    _client.check_available()


def fetch_job_list(offset: int, limit: int = 100) -> dict:
    params = {
        "job_sort":  "job.latest_order",
        "years":     -1,
        "country":   "kr",
        "locations": "all",
        "tag_type_ids": CATEGORY,
        "limit":     limit,
        "offset":    offset,
    }
    data = _client.get(BASE_URL, params=params)
    if not isinstance(data.get("data"), list) or not isinstance(data.get("links"), dict):
        raise SourceUnavailable("Wanted: 공고 목록 응답 형식이 변경되었습니다.")
    return data


def fetch_job_detail(job_id: int) -> dict:
    return _client.get(f"{BASE_URL}/{job_id}")


def collect_all_jobs(progress_cb=None) -> list[dict]:
    """서버 개발자 직무 목록을 끝까지 읽고, 웹 백엔드 공고만 상세 조회한다."""
    seen: set[int] = set()
    jobs: list[dict] = []
    offset = 0
    while True:
        data = fetch_job_list(offset)
        items = data["data"]
        new_ids = {int(item["id"]) for item in items} - seen
        if not new_ids and data["links"].get("next"):
            raise SourceUnavailable("Wanted: 같은 목록 페이지가 반복되어 수집을 중단했습니다.")
        for item in items:
            job_id = int(item["id"])
            if job_id in seen:
                continue
            seen.add(job_id)
            title = item.get("position") or item.get("title") or ""
            categories = {tag.get("id") for tag in item.get("category_tags", [])}
            if CATEGORY not in categories or not matches_backend_role(title, "backend"):
                continue
            record = _record_from_job(item)
            if not is_expired(record):
                jobs.append({"id": job_id, **record})
        if progress_cb:
            progress_cb(len(jobs))
        if not data["links"].get("next"):
            return jobs
        offset += len(items)


def extract_langs(detail_data: dict) -> list[str]:
    """저장 및 재분석과 동일하게 제목과 정제된 본문에서 기술을 추출한다."""
    job = detail_data.get("job") or {}
    return extract_job_keywords({
        "title": job.get("position") or job.get("title") or "",
        "content": _wanted_detail_markdown(job), "tech_stacks": _tech_stacks(job),
    })


def _tech_stacks(job: dict) -> list[str]:
    return [str(tag.get("title") or tag.get("name") or "")
            for tag in (job.get("skill_tags") or []) if isinstance(tag, dict)]


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
    """직무로 선별된 공고의 상세 본문을 가져온다."""
    detail = fetch_job_detail(job_id)
    job = detail.get("job", {})
    if not job:
        raise JobDetailUnavailable(f"원티드 공고 {job_id} 상세를 가져오지 못했습니다.")
    record = _record_from_job(job)
    if not record["content"]:
        raise JobDetailUnavailable(f"원티드 공고 {job_id} 상세 본문이 없습니다.")
    record["url"] = f"https://www.wanted.co.kr/wd/{job_id}"
    record["_detail_markdown"] = record["content"]
    return record


def _record_from_job(job: dict) -> dict:
    company = job.get("company") or {}
    address = job.get("address") or {}
    annual_from = job.get("annual_from") or 0
    annual_to = job.get("annual_to")
    if annual_to is None or annual_to < 0:
        annual_to = 10
    content = _wanted_detail_markdown(job)
    hints = " ".join(
        tag.get("title", "")
        for tag in [*(job.get("tags") or []), *(job.get("skill_tags") or [])]
        if isinstance(tag, dict)
    )
    return {
        "source":      "wanted",
        "job_role":    "backend",
        "title":       job.get("position") or job.get("title") or "제목 없음",
        "company":     company.get("name", ""),
        "location":    address.get("full_location") or address.get("location", ""),
        "url":         f"https://www.wanted.co.kr/wd/{job.get('id')}",
        "langs":       extract_langs({"job": job}),
        "tech_stacks": _tech_stacks(job),
        "annual_from": annual_from,
        "annual_to":   annual_to,
        **build_record_fields(
            title=job.get("position") or job.get("title") or "제목 없음",
            content=content,
            hints=hints,
            deadline=job.get("due_time"),
            status=job.get("status") or "active",
        ),
        "categories": ["backend"],
    }
