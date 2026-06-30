import re
import time
import zlib
from pathlib import Path
from urllib.parse import quote, urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .keyword_catalog import extract_keywords

BASE_URL = "https://www.saramin.co.kr"
SEARCH_KEYWORD = "백엔드"
SEARCH_URL = (
    f"{BASE_URL}/zf_user/search/recruit"
    f"?searchType=search&searchword={quote(SEARCH_KEYWORD)}&recruitSort=reg_dt"
)
KEYWORD_FILE = Path(__file__).parent / "data" / "backend" / "backend_title_keywords.txt"
MAX_WORKERS = 3
MAX_LIST_PAGES = 3
DETAIL_DELAY_SECONDS = 0.6

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

BLOCK_TEXT_PAT = re.compile(r"(captcha|보안문자|비정상|자동\s*접속|접근이\s*제한)", re.IGNORECASE)
JOB_ID_PAT = re.compile(r"(?:rec_idx|recIdx|view/)(\d+)")
EXPERIENCE_PATTERNS = (
    re.compile(r"경력\s*무관"),
    re.compile(r"신입"),
    re.compile(r"경력\s*(\d+)\s*년\s*(?:이상|↑|~)"),
    re.compile(r"(\d+)\s*년\s*(?:이상|↑)"),
    re.compile(r"(\d+)\s*년\s*[~\-]\s*(\d+)\s*년"),
)


def _load_title_keywords() -> re.Pattern:
    with open(KEYWORD_FILE, encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]
    return re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)


INCLUDE_TITLE_KEYWORDS = _load_title_keywords()


def _absolute_url(url: str) -> str:
    return urljoin(BASE_URL, url)


def _job_id_from_url(url: str) -> int:
    match = JOB_ID_PAT.search(url)
    if match:
        return int(match.group(1))
    return zlib.adler32(url.encode("utf-8"))


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _parse_experience(text: str) -> tuple[int, int]:
    text = _normalize_space(text)
    if not text:
        return 0, 10
    if EXPERIENCE_PATTERNS[0].search(text):
        return 0, 10
    if EXPERIENCE_PATTERNS[1].search(text):
        return 0, 0

    range_match = EXPERIENCE_PATTERNS[4].search(text)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))

    for pat in EXPERIENCE_PATTERNS[2:4]:
        match = pat.search(text)
        if match:
            return int(match.group(1)), 10

    return 0, 10


def _raise_if_blocked(text: str):
    if BLOCK_TEXT_PAT.search(text):
        raise RuntimeError("사람인 접근 제한 또는 보안 확인 화면이 감지되어 수집을 중단했습니다.")


def collect_all_jobs(progress_cb=None) -> list[dict]:
    """사람인 공개 검색 결과에서 백엔드 관련 공고 URL을 수집한다."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="ko-KR",
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        seen: set[str] = set()
        jobs: list[dict] = []

        for page_no in range(1, MAX_LIST_PAGES + 1):
            url = f"{SEARCH_URL}&recruitPage={page_no}"
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass

            body_text = page.locator("body").inner_text(timeout=10000)
            _raise_if_blocked(body_text)

            found = page.evaluate(
                r"""
                () => {
                    const cards = [
                        ...document.querySelectorAll('.item_recruit, .list_item, [class*="item_recruit"]')
                    ];
                    const roots = cards.length ? cards : [document.body];
                    const out = [];
                    roots.forEach(root => {
                        root.querySelectorAll('a[href*="/zf_user/jobs/relay/view"]').forEach(a => {
                            const href = a.getAttribute('href');
                            const title = (a.getAttribute('title') || a.innerText || '').trim();
                            const card = a.closest('.item_recruit, .list_item, li, tr, article, div');
                            const company = card?.querySelector('.corp_name, .company_nm, [class*="corp"]')?.innerText?.trim() || '';
                            const career = card?.querySelector('.job_condition, .career, [class*="condition"]')?.innerText?.trim() || '';
                            if (href && title) out.push({href, title, company, career});
                        });
                    });
                    return out;
                }
                """
            )

            before = len(jobs)
            for item in found:
                url = _absolute_url(item["href"])
                if url in seen:
                    continue
                title = _normalize_space(item.get("title", ""))
                if not INCLUDE_TITLE_KEYWORDS.search(title):
                    continue
                seen.add(url)
                annual_from, annual_to = _parse_experience(item.get("career", ""))
                jobs.append({
                    "id": _job_id_from_url(url),
                    "title": title,
                    "company": _normalize_space(item.get("company", "")),
                    "annual_from": annual_from,
                    "annual_to": annual_to,
                    "url": url,
                })

            if progress_cb and len(jobs) != before:
                progress_cb(len(jobs))
            if page_no > 1 and len(jobs) == before:
                break

        browser.close()
    return jobs


def _extract_detail_text(page) -> dict:
    return page.evaluate(
        r"""
        () => {
            const pick = selectors => {
                for (const selector of selectors) {
                    const el = document.querySelector(selector);
                    const text = el?.innerText?.trim();
                    if (text) return text;
                }
                return '';
            };
            return {
                title: pick(['h1', '.tit_job', '.job_tit', '[class*="tit_job"]']),
                company: pick(['.corp_name', '.company_nm', '[class*="corp_name"]']),
                career: pick(['.job_condition', '.cont .career', '[class*="condition"]']),
                detail: pick(['.job_view', '.wrap_jv_cont', '.jv_cont', 'main']) || document.body.innerText
            };
        }
        """
    )


def extract_langs(text: str) -> list[str]:
    return extract_keywords(text)


def process_job(job_meta: dict) -> dict:
    """사람인 상세 페이지에서 본문을 읽고 기술스택과 경력 정보를 보강한다."""
    time.sleep(DETAIL_DELAY_SECONDS)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.goto(job_meta["url"], wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            pass

        body_text = page.locator("body").inner_text(timeout=10000)
        _raise_if_blocked(body_text)
        detail = _extract_detail_text(page)
        browser.close()

    title = _normalize_space(detail.get("title")) or job_meta.get("title", "제목 없음")
    company = _normalize_space(detail.get("company")) or job_meta.get("company", "")
    career_text = detail.get("career")
    if career_text:
        annual_from, annual_to = _parse_experience(career_text)
    else:
        annual_from = job_meta.get("annual_from", 0)
        annual_to = job_meta.get("annual_to", 10)
    full_text = " ".join([title, company, detail.get("career", ""), detail.get("detail", "")])

    return {
        "title": title,
        "company": company,
        "annual_from": annual_from,
        "annual_to": annual_to,
        "langs": extract_langs(full_text),
    }
