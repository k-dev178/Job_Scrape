from .job_record import classify_categories, is_expired

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
        if not include_expired and is_expired(job):
            continue
        categories = job.get("categories") or classify_categories(
            str(job.get("title") or ""),
            str(job.get("content") or ""),
            " ".join(job.get("keywords") or []),
        )
        if category == "all_it":
            filtered.append(job)
        elif category == "backend" and "backend" in categories:
            filtered.append(job)
        elif category == "system" and "system" in categories:
            filtered.append(job)
    return filtered
