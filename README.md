# Job Scrape

원티드, 잡코리아, 사람인의 백엔드 채용 공고를 수집하고 공고 본문에서 기술 키워드를 집계하는 웹 앱입니다.

## 실행

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/uvicorn backend.app:app --port 8000 --reload
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다. 8000번 포트가 이미 사용 중이면 기존 프로세스를 종료하거나 `--port 8001`처럼 다른 포트를 지정합니다.

## 키워드와 캐시 재생성

`모든공고md`의 전체 공고를 읽어 프로그램 전용 키워드 파일을 다시 만들고, 그 키워드로 기존 캐시를 재분석합니다.

```bash
.venv/bin/python -m backend.build_backend_keywords && .venv/bin/python -m backend.reindex_markdown_cache
```

런타임은 [`backend/data/backend/backend_keywords.json`](backend/data/backend/backend_keywords.json)의 활성 키워드만 웹에 표시합니다.

## 구조

```text
backend/
  app.py                    API, 캐시, 수집 작업 조정
  analytics.py              경력 필터와 키워드 통계
  keyword_catalog.py        런타임 키워드 로딩과 추출
  wanted_scraper.py         원티드 수집기
  jobkorea_scraper.py       잡코리아 수집기
  saramin_scraper.py        사람인 저속 수집기
  markdown_export.py        공고별 Markdown 저장
  build_backend_keywords.py 키워드 파일 생성 명령
  reindex_markdown_cache.py 기존 캐시 재분석 명령
frontend/                    웹 화면
모든공고md/                 원티드·잡코리아·사람인 공고 원문
```

잡코리아 수집은 접근 제한을 줄이기 위해 요청을 직렬화하고 간격을 두며, 한 시간 이내의 반복 새로고침을 막습니다. 새 수집이 실패하면 기존 캐시를 사용합니다.

사람인은 IT개발·데이터 전체 목록에서 백엔드·서버개발·시스템 소프트웨어·SE·S/W·임베디드·펌웨어·미들웨어 공고를 선별합니다. 요청은 한 번에 하나씩 처리하고 목록 요청 사이 6~10초, 상세 요청 사이 4~8초 대기합니다. 반복 새로고침은 6시간 동안 제한하며 기존 공고 상세는 캐시에서 재사용합니다.

모든 사이트 탭에서 `백엔드`, `시스템 소프트웨어`, `전체` 중 표시할 공고 분야를 선택할 수 있습니다.

캐시는 분야별 결과가 아니라 IT 전체 공고 원본을 저장합니다. 각 공고에는 `title`, `content`, `deadline`, `deadline_at`, `is_expired`, `categories`가 포함되며 기본 화면에서는 마감 공고를 제외합니다. 분야 규칙을 추가한 뒤에는 외부 크롤링 없이 아래 명령으로 기존 캐시를 다시 분류할 수 있습니다.

```bash
.venv/bin/python -m backend.reindex_markdown_cache
```

조회할 때는 저장된 기술 목록과 분야를 그대로 사용하지 않고 제목·본문·직무 정보에서 다시 계산합니다. 본문이 없는 공고는 제목·직무 정보만 사용하며, Markdown의 자동 생성 메타데이터는 기술 근거에서 제외합니다. 따라서 이전 캐시와 기술별 집계가 달라질 수 있습니다.

수집 후 24시간이 지났거나 수집 범위·키워드 버전이 다른 캐시, 본문이 없는 공고가 있으면 화면에 주의사항을 표시합니다. 기존 캐시는 계속 조회할 수 있지만, 현재 전체 IT 채용 현황을 보려면 새로고침이 필요합니다. 재분석 명령은 수집 시각을 기준으로 `D-2` 같은 상대 마감일을 해석합니다.

경력 필터의 `10`은 10년 이상 구간입니다. 날짜만 있는 마감일은 한국 시간 해당 날짜 23:59:59까지 포함하며, 종료 상태인 공고는 미래 마감일이 있어도 제외합니다.

## 검증

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

테스트는 실제 채용 사이트에 요청하지 않으며 마감·분류·키워드 추출, 캐시 경고, 새로고침 실패 시 복구, API 필터 검증을 확인합니다. Playwright 버전은 Docker 이미지에 포함된 브라우저와 맞추기 위해 1.58.0으로 고정합니다.
