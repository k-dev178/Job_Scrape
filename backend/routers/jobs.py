import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..scraper import (
    MAX_WORKERS,
    collect_all_job_ids,
    count_languages,
    init_session,
    is_backend_job,
    process_job,
)

router = APIRouter()


@router.get("/scrape")
def scrape():
    q: queue.Queue = queue.Queue()

    def run():
        try:
            init_session()
            q.put({"type": "status", "msg": "공고 목록 수집 중..."})

            job_ids = collect_all_job_ids()
            q.put({
                "type": "status",
                "msg": f"총 {len(job_ids):,}개 공고 발견, 상세 분석 시작...",
                "total": len(job_ids),
            })

            texts = []
            skipped = 0
            done = 0
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {executor.submit(process_job, jid): jid for jid in job_ids}
                for future in as_completed(futures):
                    title, text = future.result()
                    done += 1
                    if not is_backend_job(title):
                        skipped += 1
                    elif text.strip():
                        texts.append(text)
                    if done % 30 == 0 or done == len(job_ids):
                        q.put({"type": "progress", "done": done, "total": len(job_ids), "skipped": skipped})

            counts = count_languages(texts)
            results = [
                {
                    "rank": i + 1,
                    "lang": lang,
                    "count": cnt,
                    "ratio": round(cnt / len(texts) * 100, 1) if texts else 0,
                }
                for i, (lang, cnt) in enumerate(sorted(counts.items(), key=lambda x: x[1], reverse=True))
            ]
            q.put({"type": "complete", "results": results, "analyzed": len(texts), "skipped": skipped})

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
