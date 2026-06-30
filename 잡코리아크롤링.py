from backend.jobkorea_scraper import collect_all_jobs, process_job
from backend.markdown_export import write_job_markdown


def main():
    """웹과 동일한 수집기로 결과를 확인할 수 있는 CLI 진입점."""
    jobs = collect_all_jobs(
        progress_cb=lambda count: print(f"잡코리아 공고 {count}개 발견")
    )
    for index, job in enumerate(jobs, start=1):
        processed = process_job(job)
        detail_markdown = processed.pop("_detail_markdown", "")
        job.update(processed)
        write_job_markdown("jobkorea", job, detail_markdown)
        print(
            f"[{index}/{len(jobs)}] {job['title']} | "
            f"{', '.join(job['langs']) or '감지 기술 없음'}"
        )

    print(f"총 {len(jobs)}개 공고 분석 완료 (웹에서는 잡코리아 탭에서 확인)")


if __name__ == "__main__":
    main()
