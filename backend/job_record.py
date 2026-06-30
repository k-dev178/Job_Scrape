"""사이트 공통 공고 레코드와 로컬 재분류 규칙."""

import re
from datetime import datetime, timedelta, timezone


BACKEND_PATTERN = re.compile(
    r"백\s*엔드|back[\s-]*end|서버\s*(?:개발|엔지니어)|"
    r"server\s*(?:developer|engineer)|spring|django|fastapi|nestjs|node\.?js",
    re.IGNORECASE,
)
SYSTEM_PATTERN = re.compile(
    r"시스템\s*(?:소프트웨어|개발|엔지니어)|system\s*(?:software|engineer)|"
    r"(?:^|\s)S/W(?:\s|$)|embedded|firmware|미들웨어|임베디드|펌웨어|"
    r"RTOS|FreeRTOS|MCU|STM32|AUTOSAR|Yocto|POSIX|MFC|Qt",
    re.IGNORECASE,
)
KST = timezone(timedelta(hours=9))


def classify_categories(title: str, content: str = "", hints: str = "") -> list[str]:
    text = " ".join([title or "", content or "", hints or ""])
    categories = []
    if BACKEND_PATTERN.search(text):
        categories.append("backend")
    if SYSTEM_PATTERN.search(text):
        categories.append("system")
    return categories


def deadline_timestamp(value) -> float | None:
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        return timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
    text = str(value).strip()
    if re.search(r"상시|채용시|수시", text):
        return None
    now_kst = datetime.now(KST)
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
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.timestamp()
    except ValueError:
        pass
    match = re.search(r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", text)
    if match:
        return datetime(
            int(match.group(1)), int(match.group(2)), int(match.group(3)),
            23, 59, 59, tzinfo=KST,
        ).timestamp()
    match = re.search(r"(?:~\s*)?(\d{1,2})[./-](\d{1,2})", text)
    if match:
        now = now_kst
        month, day = int(match.group(1)), int(match.group(2))
        year = now.year + (1 if month < now.month - 6 else 0)
        return datetime(year, month, day, 23, 59, 59, tzinfo=KST).timestamp()
    return None


def is_expired(job: dict, now: float | None = None) -> bool:
    deadline_at = job.get("deadline_at")
    if deadline_at is None:
        return str(job.get("status") or "").lower() in {"closed", "expired", "ended"}
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
