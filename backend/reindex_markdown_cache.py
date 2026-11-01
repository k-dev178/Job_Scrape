"""모든공고md 본문을 키워드 JSON 기준으로 재분석해 캐시를 갱신한다."""

import json
import re
from pathlib import Path

from .job_record import deadline_timestamp, is_expired, matches_backend_role
from .keyword_catalog import STACK_KEYWORD_SCOPE, extract_job_keywords
from .wanted_scraper import CACHE_SCOPE as WANTED_CACHE_SCOPE
from .jumpit_scraper import CACHE_SCOPE as JUMPIT_CACHE_SCOPE


PROJECT_DIR = Path(__file__).parent.parent
MARKDOWN_DIR = PROJECT_DIR / "모든공고md"
MIN_COVERAGE = 0.9
SOURCES = {
    "wanted": {
        "prefix": "원티드",
        "cache_file": Path(__file__).parent / "cache_wanted_backend.json",
        "cache_scope": f"{WANTED_CACHE_SCOPE}:{STACK_KEYWORD_SCOPE}",
        "base_scope": WANTED_CACHE_SCOPE,
    },
    "jumpit": {
        "prefix": "점핏",
        "cache_file": Path(__file__).parent / "cache_jumpit.json",
        "cache_scope": f"{JUMPIT_CACHE_SCOPE}:{STACK_KEYWORD_SCOPE}",
        "base_scope": JUMPIT_CACHE_SCOPE,
    },
}


def _markdown_index(prefix: str) -> dict[int, Path]:
    index = {}
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)_")
    for path in MARKDOWN_DIR.glob(f"{prefix}_*.md"):
        match = pattern.match(path.name)
        if match:
            job_id = int(match.group(1))
            previous = index.get(job_id)
            if previous is None or (path.stat().st_mtime_ns, path.name) > (previous.stat().st_mtime_ns, previous.name):
                index[job_id] = path
    return index


def reindex_source(source: str) -> dict:
    config = SOURCES[source]
    cache_file = config["cache_file"]
    if not cache_file.exists():
        return {
            "source": source,
            "jobs": 0,
            "matched": 0,
            "coverage": 0,
            "mode": "filtered",
            "updated": False,
        }
    cache = json.loads(cache_file.read_text(encoding="utf-8"))
    jobs = cache.get("jobs", [])
    markdown_by_id = _markdown_index(config["prefix"])
    matched = 0
    reindexed_jobs = []

    for job in jobs:
        path = markdown_by_id.get(int(job["id"]))
        updated = dict(job)
        if path:
            matched += 1
            if not updated.get("content") or path.stat().st_mtime >= updated.get("detail_fetched_at", 0):
                text = path.read_text(encoding="utf-8", errors="ignore")
                updated["content"] = re.sub(r"(?m)^- 기술:.*$", "", text)
        updated["content"] = str(updated.get("content") or "")
        updated["langs"] = extract_job_keywords(updated)
        updated["categories"] = ["backend"] if matches_backend_role(
            str(updated.get("title") or ""), str(updated.get("job_role") or ""),
        ) else []
        updated["deadline"] = str(updated.get("deadline") or "")
        updated["status"] = str(updated.get("status") or "active")
        updated["deadline_at"] = deadline_timestamp(updated.get("deadline"), reference_time=cache.get("ts"))
        updated["is_expired"] = is_expired(updated)
        reindexed_jobs.append(updated)

    coverage = matched / len(jobs) if jobs else 0
    result = {
        "source": source,
        "jobs": len(jobs),
        "matched": matched,
        "coverage": coverage,
        "mode": "full" if coverage >= MIN_COVERAGE else "filtered",
        "updated": False,
    }
    required_base_scope = config.get("base_scope")
    base_scope_is_compatible = (
        required_base_scope is None
        or str(cache.get("scope", "")).startswith(required_base_scope)
    )
    if not jobs:
        return result

    cache["jobs"] = reindexed_jobs
    cache["schema_version"] = 2
    if base_scope_is_compatible:
        cache["scope"] = config["cache_scope"]
    cache_file.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    result["updated"] = True
    return result


if __name__ == "__main__":
    for source_name in SOURCES:
        result = reindex_source(source_name)
        status = "갱신" if result["updated"] else "건너뜀"
        print(
            f"{source_name}: {status} "
            f"({result['matched']}/{result['jobs']}, "
            f"coverage={result['coverage']:.1%}, mode={result['mode']})"
        )
