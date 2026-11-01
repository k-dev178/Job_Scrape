"""사이트별 공고를 웹 표시용 기술 통계로 집계한다."""

from collections import defaultdict
import re


def deduplicate_jobs(jobs: list[dict]) -> tuple[list[dict], int]:
    """회사·제목·경력·근무지가 같은 타 사이트 공고만 보수적으로 통합한다."""
    unique = []
    groups = {}
    identities = set()
    duplicates = 0
    for original in jobs:
        job = dict(original)
        source = job.get("source", "")
        identity = (source, job.get("id"))
        if job.get("id") is not None and identity in identities:
            duplicates += 1
            continue
        identities.add(identity)
        company = re.sub(r"주식회사|\(주\)|㈜", "", str(job.get("company") or ""))
        company = re.sub(r"[^\w]", "", company).casefold()
        title = re.sub(r"[^\w]", "", str(job.get("title") or "")).casefold()
        location = str(job.get("location") or "").replace("서울특별시", "서울").replace("경기도", "경기")
        location = " ".join(location.split()[:2])
        key = (company, title, job.get("annual_from"), job.get("annual_to"), location)
        candidates = groups.setdefault(key, [])
        previous = next((candidate for candidate in candidates if source not in candidate["sources"]), None)
        if company and title and location and previous:
            previous["sources"].append(source)
            previous["langs"] = list(dict.fromkeys([*previous.get("langs", []), *job.get("langs", [])]))
            duplicates += 1
        else:
            job["sources"] = [source]
            candidates.append(job)
            unique.append(job)
    return unique, duplicates


def aggregate_results(
    jobs: list[dict],
    years_min: int = 0,
    years_max: int = 10,
) -> tuple[list[dict], int]:
    filtered = [
        job
        for job in jobs
        if (years_max == 10 or job["annual_from"] <= years_max)
        and job["annual_to"] >= years_min
    ]

    counts: dict[str, int] = defaultdict(int)
    jobs_by_keyword: dict[str, list[dict]] = defaultdict(list)
    for job in filtered:
        for keyword in dict.fromkeys(job.get("langs", [])):
            counts[keyword] += 1
            jobs_by_keyword[keyword].append({
                "id": job.get("id"),
                "source": job.get("source", ""),
                "sources": job.get("sources", []),
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
