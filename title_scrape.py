"""
백엔드 공고 제목만 전부 수집해서 titles.txt로 저장하는 스크립트
키워드 필터링 기준 설정용
"""
from backend.scraper import fetch_job_list, init_session

OUTPUT_FILE = "titles.txt"


def collect_all_titles() -> list[str]:
    titles = []
    offset = 0
    limit = 100

    while True:
        data = fetch_job_list(offset, limit)
        jobs = data.get("data", [])
        if not jobs:
            break

        for job in jobs:
            title = job.get("position", "")
            if title:
                titles.append(title)

        has_next = bool(data.get("links", {}).get("next"))
        print(f"  수집 중: {len(titles)}개", end="\r", flush=True)

        if not has_next:
            break

        offset += limit

    return titles


def main():
    print("세션 초기화 중...")
    init_session()

    print("공고 제목 수집 중...")
    titles = collect_all_titles()
    titles.sort()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(titles))

    print(f"\n총 {len(titles):,}개 제목 저장 완료 → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
