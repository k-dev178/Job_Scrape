import re
import time
import threading
from collections import defaultdict
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.wanted.co.kr/api/v4/jobs"
LIST_URL = (
    "https://www.wanted.co.kr/wdlist/518"
    "?country=kr&job_sort=job.latest_order&years=-1&locations=all"
)
KEYWORD_FILE = Path(__file__).parent / "data" / "backend" / "backend_title_keywords.txt"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.wanted.co.kr/wdlist/518?country=kr&job_sort=job.latest_order&years=-1&locations=all",
    "Origin": "https://www.wanted.co.kr",
    "x-wanted-platform": "pcweb",
}

CATEGORY = 518

BACKEND_STACKS = {
    # 언어
    "Java":             r"\bjava\b(?!script)",
    "Python":           r"\bpython\b",
    "Kotlin":           r"\bkotlin\b",
    "Go":               r"\b(?:go|golang)\b",
    "TypeScript":       r"\btypescript\b",
    "JavaScript":       r"\bjavascript\b",
    "C#":               r"c#",
    "C++":              r"c\+\+",
    "PHP":              r"\bphp\b",
    "Rust":             r"\brust\b",
    "Ruby":             r"\bruby\b(?!\s*on)",
    "Scala":            r"\bscala\b",
    # JVM 스택
    "Spring":           r"\bspring\b(?!\s*boot|\s*cloud|\s*security|\s*batch|\s*data)",
    "Spring Boot":      r"\bspring\s*boot\b",
    "Spring Batch":     r"\bspring\s*batch\b",
    "Spring Data":      r"\bspring\s*data\b",
    "Spring Security":  r"\bspring\s*security\b",
    "JPA":              r"\bjpa\b",
    "Hibernate":        r"\bhibernate\b",
    "MyBatis":          r"\bmybatis\b",
    "QueryDSL":         r"\bquerydsl\b",
    "WebFlux":          r"\bwebflux\b",
    "Gradle":           r"\bgradle\b",
    # Python 스택
    "Django":           r"\bdjango\b",
    "DRF":              r"\bdrf\b|\bdjango\s*rest\s*framework\b",
    "FastAPI":          r"\bfastapi\b",
    "Flask":            r"\bflask\b",
    "Celery":           r"\bcelery\b",
    "Airflow":          r"\bairflow\b",
    "SQLAlchemy":       r"\bsqlalchemy\b",
    "PyTorch":          r"\bpytorch\b",
    # Node / JS
    "Node.js":          r"\bnode\.?js\b",
    "NestJS":           r"\bnest\.?js\b",
    "Express":          r"\bexpress(?:\.?js)?\b",
    "TypeORM":          r"\btypeorm\b",
    # 기타 언어 프레임워크
    "Rails":            r"\b(?:ruby\s*on\s*rails|rails)\b",
    "ASP.NET":          r"\basp\.?net\b",
    ".NET":             r"\.net\b",
    "Laravel":          r"\blaravel\b",
    # DB
    "MySQL":            r"\bmysql\b",
    "PostgreSQL":       r"\b(?:postgresql|postgres)\b",
    "MariaDB":          r"\bmariadb\b",
    "Oracle":           r"\boracle\b",
    "MSSQL":            r"\b(?:mssql|sql\s*server)\b",
    "MongoDB":          r"\bmongodb\b",
    "Redis":            r"\bredis\b",
    "DynamoDB":         r"\bdynamodb\b",
    "Cassandra":        r"\bcassandra\b",
    "Elasticsearch":    r"\belasticsearch\b",
    "OpenSearch":       r"\bopensearch\b",
    "ClickHouse":       r"\bclickhouse\b",
    "Neo4j":            r"\bneo4j\b",
    "BigQuery":         r"\bbigquery\b",
    "Snowflake":        r"\bsnowflake\b",
    "Redshift":         r"\bredshift\b",
    "Aurora":           r"\baurora\b",
    # 메시지/스트림
    "Kafka":            r"\bkafka\b",
    "RabbitMQ":         r"\brabbitmq\b",
    "Kinesis":          r"\bkinesis\b",
    "SQS":              r"\bsqs\b",
    "SNS":              r"\bsns\b",
    "Spark":            r"\bspark\b",
    # 클라우드
    "AWS":              r"\baws\b",
    "GCP":              r"\bgcp\b",
    "Azure":            r"\bazure\b",
    "Naver Cloud":      r"\b(?:ncp|naver\s*cloud)\b",
    # AWS 세부
    "EC2":              r"\bec2\b",
    "S3":               r"\baws\s*s3\b|\bamazon\s*s3\b|\bs3\s*bucket\b",
    "Lambda":           r"\b(?:aws\s*)?lambda\b",
    "RDS":              r"\brds\b",
    "ECS":              r"\becs\b",
    "EKS":              r"\beks\b",
    "Fargate":          r"\bfargate\b",
    "CloudFront":       r"\bcloudfront\b",
    "CloudWatch":       r"\bcloudwatch\b",
    "ElastiCache":      r"\belasticache\b",
    "IAM":              r"\biam\b",
    # 컨테이너/오케스트레이션
    "Docker":           r"\bdocker\b",
    "Kubernetes":       r"\b(?:kubernetes|k8s)\b",
    "Helm":             r"\bhelm\b",
    "Istio":            r"\bistio\b",
    # CI/CD
    "Jenkins":          r"\bjenkins\b",
    "GitHub Actions":   r"\bgithub\s*actions\b",
    "GitLab CI":        r"\bgitlab\s*ci\b",
    "ArgoCD":           r"\bargo\s*cd\b|\bargocd\b",
    # IaC
    "Terraform":        r"\bterraform\b",
    "Ansible":          r"\bansible\b",
    # 모니터링/로깅
    "Grafana":          r"\bgrafana\b",
    "Prometheus":       r"\bprometheus\b",
    "Datadog":          r"\bdatadog\b",
    "New Relic":        r"\bnew\s*relic\b",
    "Sentry":           r"\bsentry\b",
    "ELK":              r"\belk\b",
    "Kibana":           r"\bkibana\b",
    # API / 프로토콜
    "GraphQL":          r"\bgraphql\b",
    "gRPC":             r"\bgrpc\b",
    "WebSocket":        r"\bweb\s*socket\b|\bwebsocket\b",
    "Swagger":          r"\bswagger\b",
    "OpenAPI":          r"\bopenapi\b",
    "JWT":              r"\bjwt\b",
    # 테스트
    "JUnit":            r"\bjunit\b",
    # AI 스택
    "OpenAI":           r"\bopenai\b",
    "LangChain":        r"\blangchain\b",
    "LangGraph":        r"\blanggraph\b",
}

COMPILED = {name: re.compile(pat, re.IGNORECASE) for name, pat in BACKEND_STACKS.items()}

# 제목에 backend_title_keywords.txt의 키워드가 있는 공고만 분석 (화이트리스트)
def load_title_keywords() -> re.Pattern:
    with open(KEYWORD_FILE, encoding="utf-8") as f:
        keywords = [line.strip() for line in f if line.strip()]
    pattern = "|".join(re.escape(k) for k in keywords)
    return re.compile(pattern, re.IGNORECASE)


INCLUDE_TITLE_KEYWORDS = load_title_keywords()

MAX_WORKERS = 10

_local = threading.local()


def get_session() -> requests.Session:
    if not hasattr(_local, "session"):
        s = requests.Session()
        s.headers.update(HEADERS)
        _local.session = s
    return _local.session


def init_session():
    """메인 페이지를 먼저 방문해 쿠키 획득"""
    try:
        get_session().get(
            "https://www.wanted.co.kr/wdlist/518?country=kr&job_sort=job.latest_order&years=-1&locations=all",
            timeout=10,
        )
    except requests.RequestException:
        pass


def fetch_job_list(offset: int, limit: int = 100) -> dict:
    params = {
        "job_sort":  "job.latest_order",
        "years":     -1,
        "country":   "kr",
        "locations": "all",
        "category":  CATEGORY,
        "limit":     limit,
        "offset":    offset,
    }
    for attempt in range(3):
        try:
            resp = get_session().get(BASE_URL, params=params, timeout=10)
            if resp.status_code == 429:
                time.sleep(5)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2)
    return {}


def fetch_job_detail(job_id: int) -> dict:
    url = f"{BASE_URL}/{job_id}"
    for attempt in range(2):
        try:
            resp = get_session().get(url, timeout=10)
            if resp.status_code == 429:
                time.sleep(5)
                continue
            if resp.status_code != 200:
                return {}
            return resp.json()
        except requests.RequestException:
            time.sleep(1)
    return {}


def collect_all_jobs(progress_cb=None) -> list[dict]:
    """Playwright로 /wdlist/518 스크롤 수집 → 키워드 매칭 공고 (id, title) 반환.
    프로모션/추천 공고까지 포함. annual_from/to는 상세 API에서 채워짐(process_job)."""
    pairs = _scrape_list_pairs(progress_cb)
    seen: set[int] = set()
    jobs: list[dict] = []
    for jid, title in pairs:
        if jid in seen:
            continue
        seen.add(jid)
        if INCLUDE_TITLE_KEYWORDS.search(title):
            jobs.append({"id": jid, "title": title})
    return jobs


def _scrape_list_pairs(progress_cb=None) -> list[tuple[int, str]]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[data-cy="job-card"]', timeout=15000)

        prev_count = 0
        stable = 0
        while True:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            count = page.locator('[data-cy="job-card"]').count()
            if progress_cb and count != prev_count:
                progress_cb(count)
            if count == prev_count:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            prev_count = count

        raw = page.evaluate(r"""
            () => {
                const out = [];
                document.querySelectorAll('[data-cy="job-card"]').forEach(card => {
                    const btn = card.querySelector('button[data-position-name]');
                    const a = card.querySelector('a[href*="/wd/"]');
                    if (!btn || !a) return;
                    const title = btn.getAttribute('data-position-name');
                    const m = a.getAttribute('href').match(/\/wd\/(\d+)/);
                    if (title && m) out.push([parseInt(m[1], 10), title]);
                });
                return out;
            }
        """)
        browser.close()
    return [(int(jid), t) for jid, t in raw]


def extract_langs(detail_data: dict) -> list[str]:
    """공고 상세에서 감지된 언어/기술 목록 반환"""
    job = detail_data.get("job", {})
    parts = [job.get("title", "")]

    for tag in job.get("tags", []):
        parts.append(tag.get("title", ""))

    detail = job.get("detail", {})
    for field in ("intro", "main_tasks", "requirements", "preferred_points", "benefits"):
        text = detail.get(field, "") or ""
        text = re.sub(r"<[^>]+>", " ", text)
        parts.append(text)

    full_text = " ".join(parts)
    return [lang for lang, pat in COMPILED.items() if pat.search(full_text)]


def process_job(job_id: int) -> dict:
    """공고 상세를 가져와 langs, annual_from, annual_to 반환.
    리스트는 Playwright라 연차 정보가 없어 여기서 상세 API로 채운다."""
    detail = fetch_job_detail(job_id)
    job = detail.get("job", {})
    annual_from = job.get("annual_from") or 0
    annual_to = job.get("annual_to")
    if annual_to is None or annual_to < 0:
        annual_to = 10
    return {
        "langs":       extract_langs(detail),
        "annual_from": annual_from,
        "annual_to":   annual_to,
    }


def aggregate_results(jobs: list[dict],
                      years_min: int = 0,
                      years_max: int = 10) -> tuple[list[dict], int]:
    """경력 범위로 jobs 필터링 후 언어 카운트 집계.
    반환: (results 리스트, 분석 공고 수)"""
    filtered = [
        j for j in jobs
        if j["annual_from"] <= years_max and j["annual_to"] >= years_min
    ]

    counts: dict[str, int] = defaultdict(int)
    for job in filtered:
        for lang in job.get("langs", []):
            counts[lang] += 1

    results = [
        {
            "rank":  i + 1,
            "lang":  lang,
            "count": cnt,
            "ratio": round(cnt / len(filtered) * 100, 1) if filtered else 0,
        }
        for i, (lang, cnt) in enumerate(sorted(counts.items(), key=lambda x: x[1], reverse=True))
    ]
    return results, len(filtered)
