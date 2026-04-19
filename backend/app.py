import json
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .backend_scraper import (
    MAX_WORKERS,
    aggregate_results,
    collect_all_jobs,
    init_session,
    process_job,
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
CACHE_FILE   = Path(__file__).parent / "cache.json"

# 캐시 구조: {"ts": float, "jobs": [{annual_from, annual_to, langs: [...]}, ...]}
_cache: dict = {}
if CACHE_FILE.exists():
    try:
        with open(CACHE_FILE) as f:
            _cache.update(json.load(f))
    except (json.JSONDecodeError, ValueError):
        CACHE_FILE.unlink()  # 깨진 캐시 파일 삭제


def save_cache():
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(_cache, f, ensure_ascii=False, indent=2)


app = FastAPI()


@app.get("/scrape")
def scrape(refresh: bool = False, years_min: int = 0, years_max: int = 10):
    # 캐시 있고 새로고침 요청이 아니면 → 재집계만 수행
    if not refresh and _cache.get("jobs"):
        results, analyzed = aggregate_results(_cache["jobs"], years_min, years_max)
        def generate_cached():
            yield f"data: {json.dumps({'type': 'cached', 'ts': _cache['ts']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'results': results, 'analyzed': analyzed, 'ts': _cache['ts']}, ensure_ascii=False)}\n\n"
        return StreamingResponse(
            generate_cached(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    q: queue.Queue = queue.Queue()

    def run():
        try:
            init_session()
            q.put({"type": "status", "msg": "공고 목록 수집 중... (Playwright)"})

            def list_progress(n):
                q.put({"type": "status", "msg": f"공고 목록 수집 중... {n:,}개"})

            job_metas = collect_all_jobs(progress_cb=list_progress)
            q.put({
                "type":  "status",
                "msg":   f"총 {len(job_metas):,}개 공고 발견, 상세 분석 시작...",
                "total": len(job_metas),
            })

            done = 0
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(process_job, j["id"]): j for j in job_metas}
                for future, job_meta in futures.items():
                    job_meta.update(future.result())
                    done += 1
                    if done % 10 == 0 or done == len(job_metas):
                        q.put({"type": "progress", "done": done, "total": len(job_metas)})

            ts = time.time()
            _cache.clear()
            _cache.update({"ts": ts, "jobs": job_metas})
            save_cache()

            results, analyzed = aggregate_results(job_metas, years_min, years_max)
            q.put({"type": "complete", "results": results, "analyzed": analyzed, "ts": ts})

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
