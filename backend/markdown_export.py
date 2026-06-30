import re
from pathlib import Path


OUTPUT_DIR = Path(__file__).parent.parent / "모든공고md"
SOURCE_LABELS = {
    "wanted": "원티드",
    "jobkorea": "잡코리아",
    "saramin": "사람인",
}


def _safe_filename(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:60] or "제목_없음"


def _career_text(job: dict) -> str:
    annual_from = int(job.get("annual_from") or 0)
    annual_to = int(job.get("annual_to") if job.get("annual_to") is not None else 10)
    if annual_from == 0 and annual_to == 0:
        return "신입"
    if annual_from == 0 and annual_to >= 10:
        return "경력 무관"
    if annual_from == annual_to:
        return f"{annual_from}년"
    if annual_to >= 10:
        return f"{annual_from}년 이상"
    return f"{annual_from}~{annual_to}년"


def write_job_markdown(
    source: str,
    job: dict,
    detail_markdown: str = "",
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """크롤링한 공고 한 건을 사람이 읽을 수 있는 Markdown 파일로 저장한다."""
    source_label = SOURCE_LABELS[source]
    title = str(job.get("title") or "제목 없음").strip()
    job_id = job.get("id")
    fallback_urls = {
        "wanted": f"https://www.wanted.co.kr/wd/{job_id}",
        "jobkorea": f"https://www.jobkorea.co.kr/Recruit/GI_Read/{job_id}",
        "saramin": f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={job_id}",
    }
    url = job.get("url") or fallback_urls[source]
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / (
        f"{source_label}_{job_id}_{_safe_filename(title)}.md"
    )

    metadata = [
        f"# {title}",
        "",
        f"- 출처: {source_label}",
        f"- 회사: {job.get('company') or '정보 없음'}",
        f"- 경력: {_career_text(job)}",
        f"- 원문: {url}",
        f"- 공고번호: {job_id}",
        f"- 기술: {', '.join(job.get('langs') or []) or '감지 기술 없음'}",
    ]
    location = str(job.get("location") or "").strip()
    if location:
        metadata.append(f"- 지역: {location}")

    body = detail_markdown.strip() or "## 공고 내용\n\n상세 내용을 가져오지 못했습니다."
    output_path.write_text("\n".join(metadata) + "\n\n" + body + "\n", encoding="utf-8")
    return output_path
