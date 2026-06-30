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
    return [name for name, pattern in COMPILED.items() if pattern.search(text)]
