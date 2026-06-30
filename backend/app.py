import json
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .analytics import aggregate_results
from .keyword_catalog import STACK_KEYWORD_SCOPE
from .wanted_scraper import (
    MAX_WORKERS,
    collect_all_jobs,
    init_session,
    process_job,
)
from .jobkorea_scraper import (
    CACHE_SCOPE as JOBKOREA_CACHE_SCOPE,
    MAX_WORKERS as JOBKOREA_MAX_WORKERS,
    collect_all_jobs as collect_jobkorea_jobs,
    process_job as process_jobkorea_job,
)
from .saramin_scraper import (
    CACHE_SCOPE as SARAMIN_CACHE_SCOPE,
    MAX_WORKERS as SARAMIN_MAX_WORKERS,
    collect_all_jobs as collect_saramin_jobs,
    process_job as process_saramin_job,
)
from .markdown_export import write_job_markdown

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
CACHE_FILES = {
    "wanted": Path(__file__).parent / "cache.json",
    "jobkorea": Path(__file__).parent / "cache_jobkorea.json",
    "saramin": Path(__file__).parent / "cache_saramin.json",
}
SCRAPERS = {
    "wanted": {
        "label": "Wanted",
        "cache_scope": f"wanted:{STACK_KEYWORD_SCOPE}",
        "export_markdown": True,
        "max_workers": MAX_WORKERS,
        "init": init_session,
        "collect": collect_all_jobs,
        "process": lambda job: process_job(job["id"]),
    },
    "jobkorea": {
        "label": "잡코리아",
        "export_markdown": True,
        "reuse_cached_jobs": True,
        "min_refresh_interval": 60 * 60,
        "cache_scope": f"{JOBKOREA_CACHE_SCOPE}:{STACK_KEYWORD_SCOPE}",
        "max_workers": JOBKOREA_MAX_WORKERS,
        "init": lambda: None,
        "collect": collect_jobkorea_jobs,
        "process": process_jobkorea_job,
    },
    "saramin": {
        "label": "사람인",
        "export_markdown": True,
        "reuse_cached_jobs": True,
        "min_refresh_interval": 6 * 60 * 60,
        "cache_scope": f"{SARAMIN_CACHE_SCOPE}:{STACK_KEYWORD_SCOPE}",
        "max_workers": SARAMIN_MAX_WORKERS,
        "init": lambda: None,
        "collect": collect_saramin_jobs,
        "process": process_saramin_job,
    },
}
ALL_SOURCES = ("wanted", "jobkorea", "saramin")

# 캐시 구조: {"ts": float, "scope"?: str, "jobs": [{annual_from, annual_to, langs: [...]}, ...]}
_caches: dict[str, dict] = {source: {} for source in CACHE_FILES}
_locks: dict[str, threading.Lock] = {source: threading.Lock() for source in CACHE_FILES}
for source, cache_file in CACHE_FILES.items():
    if cache_file.exists():
        try:
            with open(cache_file, encoding="utf-8") as f:
                _caches[source].update(json.load(f))
        except (json.JSONDecodeError, ValueError):
            cache_file.unlink()  # 깨진 캐시 파일 삭제


def save_cache(source: str):
    cache_file = CACHE_FILES[source]
    temporary_file = cache_file.with_suffix(cache_file.suffix + ".tmp")
    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(_caches[source], file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary_file.replace(cache_file)


def cache_is_valid(source: str) -> bool:
    scraper = SCRAPERS[source]
    cache = _caches[source]
    cache_scope = scraper.get("cache_scope")
    return bool(cache.get("jobs")) and (
        cache_scope is None or cache.get("scope") == cache_scope
    )


def scrape_source(source: str, q: queue.Queue) -> tuple[list[dict], float]:
    """단일 사이트를 새로 크롤링하고 Markdown과 사이트별 캐시를 갱신한다."""
    scraper = SCRAPERS[source]
    cache = _caches[source]
    min_refresh_interval = scraper.get("min_refresh_interval", 0)
    if (
        min_refresh_interval
        and cache_is_valid(source)
        and time.time() - cache["ts"] < min_refresh_interval
    ):
        remaining = max(
            1,
            int((min_refresh_interval - (time.time() - cache["ts"])) / 60) + 1,
        )
        raise RuntimeError(
            f"트래픽 보호를 위해 약 {remaining}분 후 새로고침할 수 있습니다."
        )
    lock = _locks[source]
    if not lock.acquire(blocking=False):
        raise RuntimeError(f"{scraper['label']} 분석이 이미 실행 중입니다.")

    try:
        scraper["init"]()
        q.put({"type": "status", "msg": f"{scraper['label']} 공고 목록 수집 중..."})

        def list_progress(count):
            q.put({
                "type": "status",
                "msg": f"{scraper['label']} 공고 목록 수집 중... {count:,}개",
            })

        job_metas = scraper["collect"](progress_cb=list_progress)
        cached_by_id = {}
        if scraper.get("reuse_cached_jobs") and cache_is_valid(source):
            cached_by_id = {
                int(job["id"]): job
                for job in cache.get("jobs", [])
            }

        pending_jobs = []
        reused = 0
        for job_meta in job_metas:
            cached_job = cached_by_id.get(int(job_meta["id"]))
            if cached_job is None or "langs" not in cached_job:
                pending_jobs.append(job_meta)
                continue
            job_meta["langs"] = list(cached_job.get("langs", []))
            reused += 1

        q.put({
            "type": "status",
            "msg": (
                f"{scraper['label']} 총 {len(job_metas):,}개 공고 발견, "
                f"기존 {reused:,}개 재사용, 신규 {len(pending_jobs):,}개 상세 분석..."
            ),
            "total": len(job_metas),
        })

        done = reused
        if done:
            q.put({
                "type": "progress",
                "done": done,
                "total": len(job_metas),
                "source": source,
                "source_label": scraper["label"],
            })
        with ThreadPoolExecutor(max_workers=scraper["max_workers"]) as executor:
            futures = {
                executor.submit(scraper["process"], job): job
                for job in pending_jobs
            }
            for future in as_completed(futures):
                job_meta = futures[future]
                processed = future.result()
                detail_markdown = processed.pop("_detail_markdown", "")
                job_meta.update(processed)
                if scraper.get("export_markdown"):
                    write_job_markdown(source, job_meta, detail_markdown)
                done += 1
                if done % 10 == 0 or done == len(job_metas):
                    q.put({
                        "type": "progress",
                        "done": done,
                        "total": len(job_metas),
                        "source": source,
                        "source_label": scraper["label"],
                    })

        timestamp = time.time()
        cache.clear()
        cache.update({"ts": timestamp, "jobs": job_metas})
        cache_scope = scraper.get("cache_scope")
        if cache_scope:
            cache["scope"] = cache_scope
        save_cache(source)
        return job_metas, timestamp
    finally:
        lock.release()


app = FastAPI()


@app.get("/scrape-status")
def scrape_status(source: str = "wanted"):
    """SSE 연결이 끊겼을 때 진행 작업과 캐시 완료 여부를 복구한다."""
    if source != "all" and source not in SCRAPERS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 source: {source}")
    requested_sources = ALL_SOURCES if source == "all" else (source,)
    valid = all(cache_is_valid(item) for item in requested_sources)
    running = any(_locks[item].locked() for item in requested_sources)
    return {
        "source": source,
        "running": running,
        "valid": valid,
        "jobs": sum(len(_caches[item].get("jobs", [])) for item in requested_sources),
        "ts": min(
            (_caches[item].get("ts", 0) for item in requested_sources),
            default=0,
        ) if valid else 0,
    }


@app.get("/scrape")
def scrape(refresh: bool = False, years_min: int = 0, years_max: int = 10, source: str = "wanted"):
    if source != "all" and source not in SCRAPERS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 source: {source}")

    requested_sources = ALL_SOURCES if source == "all" else (source,)

    # 요청한 모든 사이트의 유효 캐시가 있으면 합쳐서 즉시 재집계한다.
    if not refresh and all(cache_is_valid(item) for item in requested_sources):
        jobs = [
            job
            for item in requested_sources
            for job in _caches[item]["jobs"]
        ]
        timestamp = min(_caches[item]["ts"] for item in requested_sources)
        results, analyzed = aggregate_results(jobs, years_min, years_max)

        def generate_cached():
            yield f"data: {json.dumps({'type': 'cached', 'ts': timestamp, 'source': source}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'results': results, 'analyzed': analyzed, 'ts': timestamp, 'source': source}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            generate_cached(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    q: queue.Queue = queue.Queue()

    def run():
        try:
            combined_jobs = []
            timestamps = []
            warnings = []
            for item in requested_sources:
                if not refresh and cache_is_valid(item):
                    q.put({
                        "type": "status",
                        "msg": f"{SCRAPERS[item]['label']} 유효 캐시 사용 중...",
                    })
                    jobs = _caches[item]["jobs"]
                    timestamp = _caches[item]["ts"]
                else:
                    try:
                        jobs, timestamp = scrape_source(item, q)
                    except Exception as error:
                        if not cache_is_valid(item):
                            raise
                        warning = (
                            f"{SCRAPERS[item]['label']} 새로고침 실패: {error} "
                            "기존 캐시를 사용합니다."
                        )
                        warnings.append(warning)
                        q.put({"type": "warning", "msg": warning, "source": item})
                        jobs = _caches[item]["jobs"]
                        timestamp = _caches[item]["ts"]
                combined_jobs.extend(jobs)
                timestamps.append(timestamp)

            timestamp = min(timestamps)
            results, analyzed = aggregate_results(
                combined_jobs,
                years_min,
                years_max,
            )
            q.put({
                "type": "complete",
                "results": results,
                "analyzed": analyzed,
                "ts": timestamp,
                "source": source,
                "warnings": warnings,
            })

        except Exception as e:
            q.put({"type": "error", "msg": str(e)})
        finally:
            q.put(None)

    threading.Thread(target=run, daemon=True).start()

    def generate():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# API 라우트 등록 후 프론트엔드 정적 파일 마운트 (순서 중요)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
