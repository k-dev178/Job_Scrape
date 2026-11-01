import json
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .analytics import aggregate_results, deduplicate_jobs
from .keyword_catalog import STACK_KEYWORD_SCOPE, extract_job_keywords
from .job_filter import CATEGORIES as JOB_CATEGORIES, filter_jobs
from .job_record import KST, build_record_fields, matches_backend_role
from .wanted_scraper import (
    CACHE_SCOPE as WANTED_CACHE_SCOPE,
    MAX_WORKERS,
    collect_all_jobs,
    init_session,
    process_job,
)
from .jumpit_scraper import (
    CACHE_SCOPE as JUMPIT_CACHE_SCOPE,
    MAX_WORKERS as JUMPIT_MAX_WORKERS,
    collect_all_jobs as collect_jumpit_jobs,
    init_session as init_jumpit_session,
    process_job as process_jumpit_job,
)
from .markdown_export import write_job_markdown
from .scrape_http import JobDetailUnavailable

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
CACHE_FILES = {
    "wanted": Path(__file__).parent / "cache_wanted_backend.json",
    "jumpit": Path(__file__).parent / "cache_jumpit.json",
}
SCRAPERS = {
    "wanted": {
        "label": "Wanted",
        "collection_scope": "web_backend",
        "cache_scope": f"{WANTED_CACHE_SCOPE}:{STACK_KEYWORD_SCOPE}",
        "export_markdown": True,
        "reuse_cached_jobs": True,
        "detail_cache_ttl": 24 * 60 * 60,
        "min_refresh_interval": 60 * 60,
        "max_workers": MAX_WORKERS,
        "init": init_session,
        "collect": collect_all_jobs,
        "process": lambda job: process_job(job["id"]),
    },
    "jumpit": {
        "label": "점핏",
        "collection_scope": "web_backend",
        "export_markdown": True,
        "reuse_cached_jobs": True,
        "detail_cache_ttl": 24 * 60 * 60,
        "min_refresh_interval": 60 * 60,
        "cache_scope": f"{JUMPIT_CACHE_SCOPE}:{STACK_KEYWORD_SCOPE}",
        "max_workers": JUMPIT_MAX_WORKERS,
        "init": init_jumpit_session,
        "collect": collect_jumpit_jobs,
        "process": process_jumpit_job,
    },
}

# 캐시 구조: {"ts": float, "scope"?: str, "jobs": [{annual_from, annual_to, langs: [...]}, ...]}
_caches: dict[str, dict] = {source: {} for source in CACHE_FILES}
_locks: dict[str, threading.Lock] = {source: threading.Lock() for source in CACHE_FILES}
_runs: dict[str, dict] = {}
_runs_lock = threading.Lock()
for source, cache_file in CACHE_FILES.items():
    if source == "wanted" and not cache_file.exists():
        # 기존 IT 전체 캐시는 읽기 전용으로 활용하고 새 범위는 별도 파일에 저장한다.
        cache_file = Path(__file__).parent / "cache.json"
    if cache_file.exists():
        try:
            with open(cache_file, encoding="utf-8") as f:
                _caches[source].update(json.load(f))
        except (json.JSONDecodeError, ValueError):
            pass  # 원본을 보존하고 다음 수집에서 별도 캐시를 생성한다.


def save_cache(source: str, cache: dict):
    cache_file = CACHE_FILES[source]
    temporary_file = cache_file.with_suffix(cache_file.suffix + ".tmp")
    try:
        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(cache, file, ensure_ascii=False, indent=2)
            file.write("\n")
        temporary_file.replace(cache_file)
    finally:
        temporary_file.unlink(missing_ok=True)


def register_run(sources: tuple[str, ...]) -> str:
    run_id = uuid4().hex
    with _runs_lock:
        _runs[run_id] = {"sources": sources, "running": True, "outcome": None}
    return run_id


def finish_run(run_id: str, outcome: dict):
    with _runs_lock:
        _runs[run_id].update(running=False, outcome=outcome)
        completed = [key for key, value in _runs.items() if not value["running"]]
        for key in completed[:-10]:
            del _runs[key]


def cache_is_valid(source: str) -> bool:
    scraper = SCRAPERS[source]
    cache = _caches[source]
    cache_scope = scraper.get("cache_scope")
    return bool(cache.get("jobs")) and (
        cache_scope is None or cache.get("scope") == cache_scope
    )


def cache_source_for_read(source: str) -> str | None:
    """분석 조회는 범위가 오래됐더라도 가진 캐시를 우선 사용한다."""
    return source if _caches[source].get("jobs") else None


class RefreshCooldown(RuntimeError):
    """수집된 데이터를 재사용하는 정상적인 재수집 대기 상태."""


def collection_info(source: str) -> dict:
    cache = _caches[source]
    valid = cache_is_valid(source)
    timestamp = cache.get("ts", 0)
    stats = cache.get("collection_stats", {})
    return {
        "label": SCRAPERS[source]["label"],
        "jobs": len(cache.get("jobs", [])),
        "ts": timestamp,
        "scope_current": valid,
        "partial": bool(stats.get("failed")),
        "next_refresh_at": timestamp + SCRAPERS[source].get("min_refresh_interval", 0) if valid else None,
    }


def collection_infos(sources) -> dict:
    return {source: collection_info(source) for source in sources if _caches[source].get("jobs")}


def cache_warnings(source: str) -> list[str]:
    cache = _caches[source]
    label = SCRAPERS[source]["label"]
    warnings = []
    if not cache_is_valid(source):
        warnings.append(f"{label}: 캐시의 수집 범위 또는 키워드 기준이 현재와 다릅니다. 새로고침이 필요합니다.")
    if time.time() - cache.get("ts", 0) > 24 * 60 * 60:
        warnings.append(f"{label}: 수집한 지 24시간이 지난 데이터입니다. 현재 채용 현황과 다를 수 있습니다.")
    jobs = cache.get("jobs", [])
    missing = sum(not str(job.get("content") or "").strip() for job in jobs)
    if missing:
        warnings.append(f"{label}: {len(jobs):,}개 중 본문이 없는 {missing:,}개는 기술 통계에서 제외합니다.")
    stats = cache.get("collection_stats", {})
    if stats.get("failed"):
        collected_at = datetime.fromtimestamp(cache.get("ts", 0), KST).strftime("%m/%d %H:%M")
        warnings.append(
            f"{label}: 저장된 수집 기록 ({collected_at}) — 상세 조회 {stats['failed']:,}개 실패 · "
            f"기존 공고 {stats.get('fallback_reused', 0):,}개 재사용, "
            f"캐시 없는 공고 {stats.get('skipped', 0):,}개 제외. "
            "이번 분석에는 저장된 공고를 사용합니다."
        )
    return warnings


def scrape_source(source: str, q: queue.Queue) -> tuple[list[dict], float, dict]:
    """단일 사이트를 새로 크롤링하고 Markdown과 사이트별 캐시를 갱신한다."""
    scraper = SCRAPERS[source]
    lock = _locks[source]
    if not lock.acquire(blocking=False):
        raise RuntimeError(f"{scraper['label']} 분석이 이미 실행 중입니다.")

    try:
        cache = _caches[source]
        min_refresh_interval = scraper.get("min_refresh_interval", 0)
        elapsed = time.time() - cache.get("ts", 0)
        if min_refresh_interval and cache_is_valid(source) and elapsed < min_refresh_interval:
            info = collection_info(source)
            collected_at = datetime.fromtimestamp(info["ts"], KST).strftime("%m/%d %H:%M")
            next_refresh = datetime.fromtimestamp(info["next_refresh_at"], KST).strftime("%m/%d %H:%M")
            raise RefreshCooldown(
                f"{info['label']} {info['jobs']:,}개 {'저장 (일부 상세 미확보)' if info['partial'] else '수집 완료'} ({collected_at}). "
                f"저장된 데이터로 분석합니다. 다음 수집은 {next_refresh}부터 가능합니다."
            )
        scraper["init"]()
        q.put({
            "type": "status", "source": source, "phase": "listing",
            "msg": f"{scraper['label']} 공고 목록 수집 중...",
        })

        def list_progress(count):
            q.put({
                "type": "status",
                "source": source,
                "phase": "listing",
                "count": count,
                "msg": f"{scraper['label']} 공고 목록 수집 중... {count:,}개",
            })

        job_metas = [dict(job) for job in scraper["collect"](progress_cb=list_progress)
                     if matches_backend_role(str(job.get("title") or ""), str(job.get("job_role") or ""))]
        if not job_metas:
            raise RuntimeError(f"{scraper['label']} 공고 목록이 비어 있어 기존 캐시를 보존합니다.")
        cached_by_id = {int(job["id"]): job for job in cache.get("jobs", [])}

        pending_jobs = []
        reused = 0
        accepted_ids = set()
        for job_meta in job_metas:
            cached_job = cached_by_id.get(int(job_meta["id"]))
            detail_ts = (cached_job or {}).get("detail_fetched_at", cache.get("ts", 0))
            stale = time.time() - detail_ts > scraper.get("detail_cache_ttl", 0)
            if not scraper.get("reuse_cached_jobs") or cached_job is None or not cached_job.get("content") or stale:
                pending_jobs.append(job_meta)
                continue
            content = str(cached_job.get("content") or "")
            job_meta["tech_stacks"] = job_meta.get("tech_stacks") or cached_job.get("tech_stacks") or []
            job_meta["langs"] = extract_job_keywords({**job_meta, "content": content})
            job_meta.update(build_record_fields(
                title=str(job_meta.get("title") or cached_job.get("title") or ""),
                content=content,
                hints=(
                    " ".join(job_meta.get("keywords") or [])
                    + " " + str(job_meta.get("sectors") or "")
                ),
                deadline=job_meta["deadline"] if "deadline" in job_meta else cached_job.get("deadline"),
                status=str(job_meta.get("status") or cached_job.get("status") or "active"),
            ))
            job_meta["detail_fetched_at"] = detail_ts
            job_meta["source"] = source
            reused += 1
            accepted_ids.add(int(job_meta["id"]))

        stats = {
            "collected": len(job_metas), "succeeded": 0, "reused": reused,
            "failed": 0, "fallback_reused": 0, "skipped": 0,
        }

        q.put({
            "type": "status",
            "source": source,
            "phase": "details",
            "msg": (
                f"{scraper['label']} 총 {len(job_metas):,}개 공고 발견, "
                f"기존 {reused:,}개 재사용, 신규 {len(pending_jobs):,}개 상세 분석..."
            ),
            "total": len(job_metas),
        })

        done = reused
        last_detail_error = ""
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
            try:
                for future in as_completed(futures):
                    job_meta = futures[future]
                    job_id = int(job_meta["id"])
                    try:
                        processed = dict(future.result())
                        if not str(processed.get("content") or job_meta.get("content") or "").strip():
                            raise JobDetailUnavailable(f"공고 {job_id}: 상세 본문이 없습니다.")
                    except JobDetailUnavailable as error:
                        last_detail_error = str(error)
                        stats["failed"] += 1
                        cached_job = cached_by_id.get(job_id)
                        if cached_job and cached_job.get("content"):
                            # 조회하지 못한 상세·경력·마감은 기존 값 그대로 보존한다.
                            job_meta.clear()
                            job_meta.update(cached_job)
                            accepted_ids.add(job_id)
                            stats["reused"] += 1
                            stats["fallback_reused"] += 1
                        else:
                            stats["skipped"] += 1
                    else:
                        detail_markdown = processed.pop("_detail_markdown", "")
                        job_meta.update(processed)
                        job_meta["source"] = source
                        job_meta["detail_fetched_at"] = time.time()
                        if scraper.get("export_markdown"):
                            write_job_markdown(
                                scraper.get("markdown_source", source),
                                job_meta,
                                detail_markdown,
                            )
                        accepted_ids.add(job_id)
                        stats["succeeded"] += 1
                    done += 1
                    if done % 10 == 0 or done == len(job_metas):
                        q.put({
                            "type": "progress",
                            "done": done,
                            "total": len(job_metas),
                            "source": source,
                            "source_label": scraper["label"],
                            "reused": stats["reused"],
                        })
            except Exception:
                # 사이트 접근 제한 등 전체 오류가 나면 아직 시작하지 않은 작업을 취소한다.
                for future in futures:
                    future.cancel()
                raise

        if pending_jobs and stats["failed"] == len(pending_jobs):
            raise RuntimeError(
                f"{scraper['label']} 상세 조회 {len(pending_jobs):,}개가 모두 실패했습니다. "
                f"마지막 오류: {last_detail_error}"
            )
        jobs = [job for job in job_metas if int(job["id"]) in accepted_ids]
        jobs = [job for job in jobs if matches_backend_role(str(job.get("title") or ""), str(job.get("job_role") or ""))]
        if not jobs:
            raise RuntimeError(f"{scraper['label']}: 분석 가능한 백엔드 공고가 없습니다.")
        if stats["failed"] >= 10 and stats["failed"] > len(pending_jobs) * 0.1:
            raise RuntimeError(f"{scraper['label']}: 상세 조회 {stats['failed']:,}개 실패로 기존 캐시를 보존합니다. {last_detail_error}")

        timestamp = time.time()
        new_cache = {
            "schema_version": 2,
            "collection_scope": scraper.get("collection_scope", ""),
            "ts": timestamp,
            "jobs": jobs,
            "collection_stats": stats,
        }
        cache_scope = scraper.get("cache_scope")
        if cache_scope:
            new_cache["scope"] = cache_scope
        save_cache(source, new_cache)
        _caches[source] = new_cache
        return jobs, timestamp, stats
    finally:
        lock.release()


app = FastAPI()


def requested_sources(source: str, category: str) -> tuple[str, ...]:
    if category not in (*JOB_CATEGORIES, "all_it"):
        raise HTTPException(status_code=400, detail=f"지원하지 않는 category: {category}")
    if source == "all":
        return tuple(SCRAPERS)
    if source not in SCRAPERS:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 source: {source}")
    return (source,)


@app.get("/scrape-status")
def scrape_status(source: str = "all", category: str = "backend", run_id: str | None = None):
    """SSE 연결이 끊겼을 때 진행 작업과 캐시 완료 여부를 복구한다."""
    sources = requested_sources(source, category)
    valid = all(cache_is_valid(item) for item in sources)
    with _runs_lock:
        run = dict(_runs[run_id]) if run_id in _runs else None
        running = any(value["running"] and set(value["sources"]).intersection(sources)
                      for value in _runs.values())
    if run and run["sources"] != sources:
        raise HTTPException(status_code=400, detail="작업의 수집 사이트가 요청과 다릅니다.")
    running = run["running"] if run else running or any(_locks[item].locked() for item in sources)
    return {
        "source": source,
        "running": running,
        "valid": valid,
        "available": any(_caches[item].get("jobs") for item in sources),
        "outcome": run["outcome"] if run else None,
        "jobs": sum(len(_caches[item].get("jobs", [])) for item in sources),
        "ts": min(
            (_caches[item].get("ts", 0) for item in sources),
            default=0,
        ) if valid else 0,
    }


@app.get("/scrape")
def scrape(
    refresh: bool = False,
    cache_only: bool = False,
    years_min: int = Query(default=0, ge=0, le=10),
    years_max: int = Query(default=10, ge=0, le=10),
    source: str = "all",
    category: str = "backend",
    include_expired: bool = False,
):
    sources = requested_sources(source, category)
    category = "backend"  # 이전 클라이언트의 all_it도 현재 수집 범위만 조회한다.
    if years_min > years_max:
        raise HTTPException(status_code=400, detail="years_min은 years_max보다 클 수 없습니다.")
    if refresh and cache_only:
        raise HTTPException(status_code=400, detail="refresh와 cache_only는 함께 사용할 수 없습니다.")

    # 기존 캐시는 범위가 오래됐어도 주의사항과 함께 조회한다.
    read_sources = {item: cache_source_for_read(item) for item in sources}
    if cache_only or (not refresh and all(read_sources.values())):
        available_sources = [item for item in sources if read_sources[item]]
        jobs = [
            job
            for item in available_sources
            for job in filter_jobs(
                read_sources[item],
                _caches[read_sources[item]]["jobs"],
                category,
                include_expired,
            )
        ]
        timestamp = min((_caches[item]["ts"] for item in available_sources), default=0)
        jobs, deduplicated = deduplicate_jobs(jobs)
        results, analyzed = aggregate_results(jobs, years_min, years_max)
        warnings = [warning for item in available_sources for warning in cache_warnings(item)]
        warnings.extend(f"{SCRAPERS[item]['label']}: 저장된 데이터가 없어 이번 분석에서 제외했습니다."
                        for item in sources if not read_sources[item])
        saved_collections = collection_infos(available_sources)
        outcome = {
            "type": "complete", "results": results, "analyzed": analyzed, "ts": timestamp,
            "analyzed_at": time.time(), "source": source, "warnings": warnings,
            "deduplicated": deduplicated, "collection_info": saved_collections,
        }

        def generate_cached():
            if not available_sources:
                yield f"data: {json.dumps({'type': 'error', 'msg': '저장된 공고가 없습니다. 수집을 시작해 주세요.'}, ensure_ascii=False)}\n\n"
                return
            yield f"data: {json.dumps({'type': 'cached', 'ts': timestamp, 'source': source}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps(outcome, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            generate_cached(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    q: queue.Queue = queue.Queue()
    run_id = register_run(sources)
    q.put({"type": "started", "run_id": run_id})

    def run():
        outcome = {"type": "error", "msg": "수집 작업이 완료되지 않았습니다."}
        try:
            combined_jobs = []
            timestamps = []
            warnings = []
            notices = []
            collection_stats = {}
            for item in sources:
                read_source = cache_source_for_read(item)
                if not refresh and read_source:
                    q.put({
                        "type": "status",
                        "source": item,
                        "phase": "cached",
                        "msg": f"{SCRAPERS[item]['label']} 기존 캐시 사용 중...",
                    })
                    jobs = _caches[read_source]["jobs"]
                    timestamp = _caches[read_source]["ts"]
                else:
                    try:
                        jobs, timestamp, stats = scrape_source(item, q)
                        collection_stats[item] = stats
                    except RefreshCooldown as notice:
                        message = str(notice)
                        notices.append(message)
                        q.put({"type": "notice", "msg": message, "source": item})
                        jobs = _caches[item]["jobs"]
                        timestamp = _caches[item]["ts"]
                        collection_stats[item] = {"succeeded": 0, "reused": len(jobs), "skipped": 0}
                    except Exception as error:
                        cached_jobs = _caches[item].get("jobs", [])
                        warning = (
                            f"{SCRAPERS[item]['label']} 새로고침 실패: {error} "
                            + ("기존 캐시를 사용합니다." if cached_jobs else "이 사이트를 제외하고 계속합니다.")
                        )
                        warnings.append(warning)
                        q.put({"type": "warning", "msg": warning, "source": item})
                        if not cached_jobs:
                            continue
                        jobs = cached_jobs
                        timestamp = _caches[item]["ts"]
                        collection_stats[item] = {"succeeded": 0, "reused": len(jobs), "skipped": 0}
                combined_jobs.extend(filter_jobs(
                    read_source or item,
                    jobs,
                    category,
                    include_expired,
                ))
                timestamps.append(timestamp)
                warnings.extend(cache_warnings(item))

            if not timestamps:
                raise RuntimeError("선택한 사이트의 공고를 가져오지 못했습니다. " + " / ".join(warnings))
            timestamp = min(timestamps)
            combined_jobs, deduplicated = deduplicate_jobs(combined_jobs)
            results, analyzed = aggregate_results(
                combined_jobs,
                years_min,
                years_max,
            )
            outcome = {
                "type": "complete",
                "results": results,
                "analyzed": analyzed,
                "ts": timestamp,
                "analyzed_at": time.time(),
                "source": source,
                "warnings": warnings,
                "notices": notices,
                "collection_info": collection_infos(sources),
                "collection_stats": collection_stats,
                "deduplicated": deduplicated,
            }

        except Exception as e:
            outcome = {"type": "error", "msg": str(e)}
        finally:
            finish_run(run_id, outcome)
            q.put(outcome)
            q.put(None)

    threading.Thread(target=run, daemon=True).start()

    def generate():
        while True:
            try:
                item = q.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
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
