"""사이트별 공고를 웹 표시용 기술 통계로 집계한다."""

from collections import defaultdict


def aggregate_results(
    jobs: list[dict],
    years_min: int = 0,
    years_max: int = 10,
) -> tuple[list[dict], int]:
    filtered = [
        job
        for job in jobs
        if job["annual_from"] <= years_max and job["annual_to"] >= years_min
    ]

    counts: dict[str, int] = defaultdict(int)
    jobs_by_keyword: dict[str, list[dict]] = defaultdict(list)
    for job in filtered:
        for keyword in job.get("langs", []):
            counts[keyword] += 1
            jobs_by_keyword[keyword].append({
                "id": job.get("id"),
                "title": job.get("title", "제목 없음"),
                "company": job.get("company", ""),
                "annual_from": job.get("annual_from", 0),
                "annual_to": job.get("annual_to", 10),
                "url": job.get("url") or f"https://www.wanted.co.kr/wd/{job.get('id')}",
                "categories": job.get("categories", []),
                "deadline": job.get("deadline", ""),
                "deadline_at": job.get("deadline_at"),
                "is_expired": job.get("is_expired", False),
            })

    results = [
        {
            "rank": index + 1,
            "lang": keyword,
            "count": count,
            "ratio": round(count / len(filtered) * 100, 1) if filtered else 0,
            "jobs": jobs_by_keyword[keyword],
        }
        for index, (keyword, count) in enumerate(
            sorted(counts.items(), key=lambda item: item[1], reverse=True)
        )
    ]
    return results, len(filtered)
