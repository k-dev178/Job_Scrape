import re

from .job_record import classify_categories, deadline_timestamp, is_expired
from .keyword_catalog import extract_keywords

"""사이트 공통 채용 분야 필터."""

CATEGORIES = ("backend", "system", "all_it")


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
        hints = " ".join(job.get("keywords") or []) + " " + str(job.get("sectors") or "")
        job["langs"] = extract_keywords(" ".join([title, content, hints]))
        if re.fullmatch(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", str(job.get("deadline") or "").strip()):
            job["deadline_at"] = deadline_timestamp(job["deadline"])
        job["is_expired"] = is_expired(job)
        if not include_expired and is_expired(job):
            continue
        categories = classify_categories(title, content, hints)
        job["categories"] = categories
        if category == "all_it":
            filtered.append(job)
        elif category == "backend" and "backend" in categories:
            filtered.append(job)
        elif category == "system" and "system" in categories:
            filtered.append(job)
    return filtered
