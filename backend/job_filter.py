import re

from .job_record import deadline_timestamp, is_expired, matches_backend_role
from .keyword_catalog import extract_job_keywords

"""사이트 공통 채용 분야 필터."""

CATEGORIES = ("backend",)


def filter_jobs(
    source: str,
    jobs: list[dict],
    category: str,
    include_expired: bool = False,
) -> list[dict]:
    if category not in CATEGORIES:
        raise ValueError(f"지원하지 않는 공고 분야: {category}")
    filtered = []
    for job in jobs:
        # 저장된 분류/기술을 신뢰하지 않고 원문으로 재계산한다. 원본 캐시는 보존한다.
        job = dict(job)
        title = str(job.get("title") or "")
        content = str(job.get("content") or "")
        if not matches_backend_role(title, str(job.get("job_role") or "")) or not content.strip():
            continue
        job["langs"] = extract_job_keywords(job)
        job["source"] = source
        job["sources"] = [source]
        if re.fullmatch(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", str(job.get("deadline") or "").strip()):
            job["deadline_at"] = deadline_timestamp(job["deadline"])
        job["is_expired"] = is_expired(job)
        if not include_expired and is_expired(job):
            continue
        job["categories"] = ["backend"]
        filtered.append(job)
    return filtered
