"""모든공고md 본문을 키워드 JSON 기준으로 재분석해 캐시를 갱신한다."""

import json
import re
from pathlib import Path

from .keyword_catalog import COMPILED, STACK_KEYWORD_SCOPE
from .jobkorea_scraper import CACHE_SCOPE as JOBKOREA_CACHE_SCOPE
from .saramin_scraper import CACHE_SCOPE as SARAMIN_CACHE_SCOPE


PROJECT_DIR = Path(__file__).parent.parent
MARKDOWN_DIR = PROJECT_DIR / "모든공고md"
MIN_COVERAGE = 0.9
SOURCES = {
    "wanted": {
        "prefix": "원티드",
        "cache_file": Path(__file__).parent / "cache.json",
        "cache_scope": f"wanted:{STACK_KEYWORD_SCOPE}",
    },
    "jobkorea": {
        "prefix": "잡코리아",
        "cache_file": Path(__file__).parent / "cache_jobkorea.json",
        "cache_scope": f"{JOBKOREA_CACHE_SCOPE}:{STACK_KEYWORD_SCOPE}",
    },
    "saramin": {
        "prefix": "사람인",
        "cache_file": Path(__file__).parent / "cache_saramin.json",
        "cache_scope": f"{SARAMIN_CACHE_SCOPE}:{STACK_KEYWORD_SCOPE}",
    },
}


def _markdown_index(prefix: str) -> dict[int, Path]:
    index = {}
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)_")
    for path in MARKDOWN_DIR.glob(f"{prefix}_*.md"):
        match = pattern.match(path.name)
        if match:
            index[int(match.group(1))] = path
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
    allowed_keywords = set(COMPILED)

    for job in jobs:
        path = markdown_by_id.get(int(job["id"]))
        if not path:
            updated = dict(job)
            updated["langs"] = [
                name for name in job.get("langs", [])
                if name in allowed_keywords
            ]
            reindexed_jobs.append(updated)
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        text = re.sub(r"(?m)^- 기술:.*$", "", text)
        updated = dict(job)
        updated["langs"] = [
            name for name, pattern in COMPILED.items() if pattern.search(text)
        ]
        reindexed_jobs.append(updated)
        matched += 1

    coverage = matched / len(jobs) if jobs else 0
    result = {
        "source": source,
        "jobs": len(jobs),
        "matched": matched,
        "coverage": coverage,
        "mode": "full" if coverage >= MIN_COVERAGE else "filtered",
        "updated": False,
    }
    required_base_scope = {
        "jobkorea": JOBKOREA_CACHE_SCOPE,
        "saramin": SARAMIN_CACHE_SCOPE,
    }.get(source)
    base_scope_is_compatible = (
        required_base_scope is None
        or str(cache.get("scope", "")).startswith(required_base_scope)
    )
    if not jobs or not base_scope_is_compatible:
        return result

    cache["jobs"] = reindexed_jobs
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
