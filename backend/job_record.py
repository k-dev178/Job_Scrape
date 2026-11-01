"""사이트 공통 공고 레코드와 로컬 재분류 규칙."""

import re
from datetime import datetime, timedelta, timezone


BACKEND_PATTERN = re.compile(
    r"백\s*엔드|back[\s-]*end|서버\s*(?:개발|엔지니어)|"
    r"server[\s-]*(?:developer|engineer)",
    re.IGNORECASE,
)
OTHER_ROLE_PATTERN = re.compile(
    r"프론트[\s-]*엔드|front[\s-]*end|풀[\s-]*스택|full[\s-]*stack|"
    r"게임|\bgame\b|devops|\bsre\b|인프라|infrastructure|"
    r"임베디드|펌웨어|embedded|firmware|시스템\s*소프트웨어|system\s*software|"
    r"데이터\s*(?:엔지니어|사이언티스트)|data\s*(?:engineer|scientist)|"
    r"머신러닝|machine\s*learning|\bml\s*engineer|모델\s*(?:개발|학습)|"
    r"\bQA\b|품질\s*(?:관리|보증)|기술\s*지원|technical\s*support|"
    r"안드로이드|android|\bios\b|모바일|mobile|웹\s*퍼블리셔|"
    r"robotics\s*engineer|로봇\s*(?:제어|엔지니어)|\bDBA\b|"
    r"네트워크\s*엔지니어|network\s*engineer",
    re.IGNORECASE,
)
SYSTEM_PATTERN = re.compile(
    r"시스템\s*(?:소프트웨어|개발|엔지니어)|system\s*(?:software|engineer)|"
    r"(?:^|\s)S/W(?:\s|$)|embedded|firmware|미들웨어|임베디드|펌웨어|"
    r"\b(?:RTOS|FreeRTOS|MCU|STM32|AUTOSAR|Yocto|POSIX|MFC|Qt)\b",
    re.IGNORECASE,
)
KST = timezone(timedelta(hours=9))


def matches_backend_role(title: str, role: str = "") -> bool:
    """기술 언급 없이 제목과 사이트의 직무 분류로 웹 백엔드를 선별한다."""
    if OTHER_ROLE_PATTERN.search(title or ""):
        return False
    return bool(BACKEND_PATTERN.search(title or "") or role == "backend")


def classify_categories(title: str, content: str = "", hints: str = "") -> list[str]:
    content = re.sub(r"(?m)^- (?:기술|분야):.*$", "", content or "")
    text = " ".join([title or "", content or "", hints or ""])
    categories = []
    if BACKEND_PATTERN.search(text):
        categories.append("backend")
    if SYSTEM_PATTERN.search(text):
        categories.append("system")
    return categories


def deadline_timestamp(value, *, reference_time: float | None = None) -> float | None:
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        return timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
    text = str(value).strip()
    if re.search(r"상시|채용시|수시", text):
        return None
    now_kst = datetime.now(KST) if reference_time is None else datetime.fromtimestamp(reference_time, KST)
    relative_match = re.search(r"D-(\d+)", text, re.IGNORECASE)
    if relative_match:
        target = now_kst + timedelta(days=int(relative_match.group(1)))
        return target.replace(hour=23, minute=59, second=59, microsecond=0).timestamp()
    if "오늘마감" in text:
        return now_kst.replace(hour=23, minute=59, second=59, microsecond=0).timestamp()
    if "내일마감" in text:
        target = now_kst + timedelta(days=1)
        return target.replace(hour=23, minute=59, second=59, microsecond=0).timestamp()
    try:
        if re.fullmatch(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", text):
            year, month, day = map(int, re.split(r"[./-]", text))
            return datetime(year, month, day, 23, 59, 59, tzinfo=KST).timestamp()
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.timestamp()
    except ValueError:
        pass
    match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", text)
    if match:
        try:
            return datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3)),
                23, 59, 59, tzinfo=KST,
            ).timestamp()
        except ValueError:
            return None
    match = re.search(r"(?:~\s*)?(\d{1,2})[./-](\d{1,2})", text)
    if match:
        now = now_kst
        month, day = int(match.group(1)), int(match.group(2))
        year = now.year + (1 if month < now.month - 6 else 0)
        try:
            return datetime(year, month, day, 23, 59, 59, tzinfo=KST).timestamp()
        except ValueError:
            return None
    return None


def is_expired(job: dict, now: float | None = None) -> bool:
    if str(job.get("status") or "").strip().lower() in {"closed", "expired", "ended"}:
        return True
    deadline_at = job.get("deadline_at")
    if deadline_at is None:
        return False
    current = datetime.now(timezone.utc).timestamp() if now is None else now
    return float(deadline_at) < current


def build_record_fields(
    *,
    title: str,
    content: str,
    hints: str = "",
    deadline=None,
    status: str = "active",
) -> dict:
    deadline_at = deadline_timestamp(deadline)
    record = {
        "content": content,
        "deadline": str(deadline or ""),
        "deadline_at": deadline_at,
        "status": status,
        "categories": classify_categories(title, content, hints),
    }
    record["is_expired"] = is_expired(record)
    return record
