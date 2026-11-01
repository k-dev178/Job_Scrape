"""런타임에서 사용하는 백엔드 기술 키워드 카탈로그."""

import hashlib
import json
import re
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data" / "backend"
STACK_KEYWORD_FILE = DATA_DIR / "backend_keywords.json"
TITLE_KEYWORD_FILE = DATA_DIR / "backend_title_keywords.txt"


def _load_backend_stacks() -> dict[str, str]:
    """문서 코퍼스에서 생성된 키워드 파일만 집계 기준으로 사용한다."""
    with STACK_KEYWORD_FILE.open(encoding="utf-8") as file:
        payload = json.load(file)
    stacks = {
        item["name"]: item["pattern"]
        for item in payload.get("keywords", [])
        if item.get("enabled", True)
    }
    if not stacks:
        raise RuntimeError(f"백엔드 키워드 파일이 비어 있습니다: {STACK_KEYWORD_FILE}")
    return stacks


def _load_title_keywords() -> re.Pattern:
    keywords = [
        line.strip()
        for line in TITLE_KEYWORD_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not keywords:
        raise RuntimeError(f"제목 키워드 파일이 비어 있습니다: {TITLE_KEYWORD_FILE}")
    return re.compile("|".join(re.escape(keyword) for keyword in keywords), re.IGNORECASE)


BACKEND_STACKS = _load_backend_stacks()
STACK_KEYWORD_SCOPE = "backend-keywords:" + hashlib.sha256(
    STACK_KEYWORD_FILE.read_bytes()
).hexdigest()[:16]
COMPILED = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in BACKEND_STACKS.items()
}
INCLUDE_TITLE_KEYWORDS = _load_title_keywords()


def extract_keywords(text: str) -> list[str]:
    """카탈로그에 등록된 기술 중 본문에 등장하는 기술만 반환한다."""
    # Markdown 내 자동 생성 메타데이터를 다시 기술 근거로 사용하지 않는다.
    text = re.sub(r"(?m)^- (?:출처|회사|경력|원문|공고번호|기술|분야|마감|지역):.*$", "", text)
    return [name for name, pattern in COMPILED.items() if pattern.search(text)]


def technical_content(content: str) -> str:
    """분리된 공고 본문에서는 업무·자격·우대 사항만 기술 근거로 사용한다."""
    include = {"주요업무", "자격요건", "우대사항", "공고내용"}
    exclude = {"회사소개", "혜택및복지", "복지및혜택"}
    sections = include | exclude
    lines = str(content or "").splitlines()
    headings = [re.match(r"^##\s+(.+?)\s*$", line) for line in lines]
    if not any(match and re.sub(r"\s", "", match.group(1)) in sections for match in headings):
        return content
    selected = []
    keep = False
    for line, heading in zip(lines, headings):
        if heading:
            name = re.sub(r"\s", "", heading.group(1))
            if name in sections:
                keep = name in include
        if keep:
            selected.append(line)
    return "\n".join(selected)


def extract_job_keywords(job: dict) -> list[str]:
    return extract_keywords(" ".join([
        str(job.get("title") or ""),
        technical_content(str(job.get("content") or "")),
        " ".join(job.get("tech_stacks") or []),
    ]))
