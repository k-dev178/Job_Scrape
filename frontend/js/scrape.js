let selectedLang = null;
let latestResultsByLang = new Map();
let selectedSource = 'all';
let selectedJobCategory = 'backend';
let activeAnalysis = 0;

const SOURCE_LABELS = {
  all: '전체',
  wanted: 'Wanted',
  jumpit: '점핏'
};

const SOURCE_DESCRIPTIONS = {
  all: 'Wanted·점핏의 웹 백엔드·서버 개발 공고를 통합 분석',
  wanted: 'Wanted 서버 개발자 직무의 웹 백엔드 공고 분석',
  jumpit: '점핏 서버/백엔드 개발자 직무의 웹 백엔드 공고 분석'
};

const CATEGORY_LABELS = {
  backend: '웹 백엔드·서버 개발'
};

function updateSourceDescription() {
  document.getElementById('source-description').textContent =
    `${SOURCE_DESCRIPTIONS[selectedSource]} · 분야: ${CATEGORY_LABELS[selectedJobCategory]}`;
}

function clearAnalysisView() {
  selectedLang = null;
  latestResultsByLang = new Map();
  ['result-box', 'summary-box', 'btn-refresh', 'last-refreshed',
   'collection-notice', 'error-box', 'status-box'].forEach(id => {
    document.getElementById(id).style.display = 'none';
  });
  closeJobList();
}

function selectSource(source) {
  selectedSource = source;
  selectedLang = null;

  document.querySelectorAll('.source-option').forEach(option => {
    const active = option.dataset.source === source;
    option.classList.toggle('active', active);
    option.setAttribute('aria-pressed', String(active));
  });

  updateSourceDescription();
  clearAnalysisView();
}

function selectJobCategory(category) {
  selectedJobCategory = category;
  selectedLang = null;
  updateSourceDescription();
  clearAnalysisView();
}

function onExpiredFilterChange() {
  clearAnalysisView();
}

function formatCareerRange(job) {
  const from = Number(job.annual_from || 0);
  const to = Number(job.annual_to ?? 10);

  if (from === 0 && to === 0) return '신입';
  if (from <= 0 && to >= 10) return '경력 전체';
  if (from <= 0) return `${to}년 이하`;
  if (to >= 10) return `${from}년 이상`;
  if (from === to) return `${from}년`;
  return `${from}년 ~ ${to}년`;
}

function formatJobCategories(job) {
  const labels = { backend: '백엔드·서버 개발' };
  return (job.categories || []).map(category => labels[category] || category).join(', ');
}

function formatDeadline(job) {
  if (job.is_expired) return job.deadline_at
    ? `마감 ${new Date(Number(job.deadline_at) * 1000).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' })}`
    : '마감';
  if (!job.deadline_at) return job.deadline || '상시';
  const expired = Number(job.deadline_at) * 1000 < Date.now();
  const date = new Date(Number(job.deadline_at) * 1000).toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' });
  return expired ? `마감 ${date}` : `~ ${date}`;
}

function buildJobListPanel(result) {
  const panel = document.createElement('div');
  panel.className = 'job-list-box';

  const header = document.createElement('div');
  header.className = 'job-list-header';

  const headingWrap = document.createElement('div');
  const kicker = document.createElement('p');
  kicker.className = 'job-list-kicker';
  kicker.textContent = '선택한 기술';

  const title = document.createElement('h2');
  title.className = 'job-list-title';

  const jobs = result.jobs || [];
  title.textContent = `${result.lang} 포함 공고 ${jobs.length.toLocaleString()}개`;

  headingWrap.append(kicker, title);

  const close = document.createElement('button');
  close.className = 'job-list-close';
  close.type = 'button';
  close.setAttribute('aria-label', '공고 목록 닫기');
  close.textContent = '✕';
  close.addEventListener('click', closeJobList);

  header.append(headingWrap, close);

  const body = document.createElement('div');
  body.className = 'job-list-body';

  if (jobs.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'job-list-empty';
    empty.textContent = '표시할 공고가 없습니다.';
    body.appendChild(empty);
  } else {
    jobs.forEach((job, index) => {
      const item = document.createElement('a');
      item.className = 'job-list-item';
      item.href = job.url;
      item.target = '_blank';
      item.rel = 'noopener noreferrer';
      item.setAttribute('aria-label', `${job.title} 공고 열기`);

      const number = document.createElement('span');
      number.className = 'job-index';
      number.textContent = String(index + 1);

      const content = document.createElement('span');
      content.className = 'job-content';

      const jobTitle = document.createElement('span');
      jobTitle.className = 'job-title';
      jobTitle.textContent = job.title;

      const meta = document.createElement('span');
      meta.className = 'job-meta';
      meta.textContent = [
        job.company,
        (job.sources || [job.source]).map(source => SOURCE_LABELS[source]).filter(Boolean).join('·'),
        formatJobCategories(job),
        formatCareerRange(job),
        formatDeadline(job)
      ].filter(Boolean).join(' · ');

      const openIcon = document.createElement('span');
      openIcon.className = 'job-open-icon';
      openIcon.setAttribute('aria-hidden', 'true');
      openIcon.textContent = '↗';

      content.append(jobTitle, meta);
      item.append(number, content, openIcon);
      body.appendChild(item);
    });
  }

  panel.append(header, body);
  return panel;
}

function closeJobList() {
  selectedLang = null;

  document.querySelectorAll('#result-body tr').forEach(row => {
    row.classList.remove('selected-lang-row');
    row.children[1]?.setAttribute('aria-pressed', 'false');
  });
  document.querySelectorAll('.job-list-inline-row').forEach(row => row.remove());

  const box = document.getElementById('job-list-box');
  if (box) box.style.display = 'none';

  window.dispatchEvent(new CustomEvent('language:selected', {
    detail: { lang: null }
  }));
}

function renderLanguageJobs(lang, selectedRow = null) {
  const result = lang ? latestResultsByLang.get(lang) : null;

  document.querySelectorAll('.job-list-inline-row').forEach(row => row.remove());
  if (!result) {
    const box = document.getElementById('job-list-box');
    if (box) box.style.display = 'none';
    selectedLang = null;
    return;
  }

  if (selectedRow) {
    const inlineRow = document.createElement('tr');
    inlineRow.className = 'job-list-inline-row';

    const cell = document.createElement('td');
    cell.colSpan = 4;
    cell.appendChild(buildJobListPanel(result));

    inlineRow.appendChild(cell);
    selectedRow.after(inlineRow);
    return;
  }

  const box = document.getElementById('job-list-box');
  if (box) {
    box.replaceChildren(...buildJobListPanel(result).childNodes);
    box.style.display = 'block';
  }
}

function selectLanguage(lang, tbody) {
  selectedLang = selectedLang === lang ? null : lang;
  let selectedRow = null;

  tbody.querySelectorAll('tr:not(.job-list-inline-row)').forEach(row => {
    const active = row.dataset.lang === selectedLang;
    row.classList.toggle('selected-lang-row', active);
    row.children[1]?.setAttribute('aria-pressed', String(active));
    if (active) selectedRow = row;
  });

  window.dispatchEvent(new CustomEvent('language:selected', {
    detail: { lang: selectedLang }
  }));

  renderLanguageJobs(selectedLang, selectedRow);
}

function bindLanguageTable(tbody) {
  tbody.onclick = event => {
    const cell = event.target.closest('td.lang-cell');
    if (!cell || !tbody.contains(cell)) return;

    selectLanguage(cell.parentElement.dataset.lang, tbody);
  };

  tbody.onkeydown = event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;

    const cell = event.target.closest('td.lang-cell');
    if (!cell || !tbody.contains(cell)) return;

    event.preventDefault();
    selectLanguage(cell.parentElement.dataset.lang, tbody);
  };
}

function setAnalysisFiltersDisabled(disabled) {
  document.querySelectorAll('.source-option, #job-category, #include-expired, #btn-career, #btn-apply')
    .forEach(control => { control.disabled = disabled; });
}

function startScrape(refresh = false, cacheOnly = false) {
  const requestId = ++activeAnalysis;
  const requestSource = selectedSource;
  const requestCategory = selectedJobCategory;
  const includeExpired = document.getElementById('include-expired').checked;
  const btn      = document.getElementById('btn');
  const btnText  = document.getElementById('btn-text');
  const btnRefresh = document.getElementById('btn-refresh');
  const statusBox  = document.getElementById('status-box');
  const resultBox  = document.getElementById('result-box');
  const errorBox   = document.getElementById('error-box');
  const collectionNotice = document.getElementById('collection-notice');
  const summaryBox = document.getElementById('summary-box');
  const jobListBox = document.getElementById('job-list-box');
  selectedLang = null;

  btn.disabled = true;
  setAnalysisFiltersDisabled(true);
  btnRefresh.disabled = true;
  btn.classList.add('loading');
  btnText.textContent = '분석 중...';

  statusBox.style.display  = 'block';
  resultBox.style.display  = 'none';
  errorBox.style.display   = 'none';
  errorBox.classList.remove('warning');
  collectionNotice.style.display = 'none';
  collectionNotice.textContent = '';
  summaryBox.style.display = 'none';
  jobListBox.style.display = 'none';

  document.getElementById('result-body').innerHTML    = '';
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('eta-text').textContent     = '';
  document.getElementById('meta-text').textContent    = '';
  document.getElementById('btn-dismiss').style.display = 'none';

  let startTime = null;
  let progressSource = null;
  let progressStartDone = 0;
  const warnings = [];
  const notices = [];
  const scrapeStart = Date.now();
  let fromCache = false;
  let runId = null;
  let settled = false;
  let recovering = false;

  const { years_min, years_max } = (typeof getCareerParams === 'function') ? getCareerParams() : { years_min: 0, years_max: 10 };
  const params = new URLSearchParams({
    years_min,
    years_max,
    source: requestSource,
    category: requestCategory,
    include_expired: includeExpired
  });
  if (refresh) params.set('refresh', 'true');
  if (cacheOnly) params.set('cache_only', 'true');
  const es = new EventSource(`/scrape?${params}`);

  const handleData = data => {
    if (settled || requestId !== activeAnalysis) return;

    if (data.type === 'started') {
      runId = data.run_id;
    }

    else if (data.type === 'cached') {
      fromCache = true;
      const age = Math.round((Date.now() / 1000 - data.ts) / 60);
      document.getElementById('status-text').textContent = `${SOURCE_LABELS[requestSource]} 저장된 데이터 불러오는 중... (${age}분 전 수집)`;
    }

    else if (data.type === 'status') {
      document.getElementById('status-text').textContent = data.msg;
      if (data.phase === 'listing' || data.phase === 'cached' || data.total !== undefined ||
          (data.source && progressSource !== data.source)) {
        startTime = null;
        progressSource = data.source || null;
        progressStartDone = 0;
        document.getElementById('progress-bar').style.width = '0%';
        document.getElementById('eta-text').textContent = '';
        document.getElementById('meta-text').textContent = data.total !== undefined
          ? `총 ${data.total.toLocaleString()}개 공고`
          : '';
      }
    }

    else if (data.type === 'progress') {
      if (!startTime || progressSource !== data.source) {
        startTime = Date.now();
        progressSource = data.source;
        progressStartDone = data.done;
      }

      const pct = Math.round(data.done / data.total * 100);
      document.getElementById('progress-bar').style.width = pct + '%';
      document.getElementById('status-text').textContent =
        `${data.source_label ? data.source_label + ' ' : ''}상세 분석 중... ${data.done.toLocaleString()} / ${data.total.toLocaleString()} (${pct}%)`;
      document.getElementById('meta-text').textContent =
        `${data.done.toLocaleString()} / ${data.total.toLocaleString()}개`;

      const elapsed   = (Date.now() - startTime) / 1000;
      const rate      = (data.done - progressStartDone) / elapsed;
      const remaining = Math.round((data.total - data.done) / rate);
      document.getElementById('eta-text').textContent = '';
      if (remaining > 0 && isFinite(remaining)) {
        const m = Math.floor(remaining / 60);
        const s = remaining % 60;
        document.getElementById('eta-text').textContent =
          m > 0 ? `약 ${m}분 ${s}초 남음` : `약 ${s}초 남음`;
      }
    }

    else if (data.type === 'notice') {
      notices.push(data.msg);
      collectionNotice.textContent = notices.join('\n');
      collectionNotice.style.display = 'block';
    }

    else if (data.type === 'warning') {
      warnings.push(data.msg);
      errorBox.textContent = '주의: ' + warnings.join(' / ');
      errorBox.classList.add('warning');
      errorBox.style.display = 'block';
    }

    else if (data.type === 'complete') {
      const elapsed = ((Date.now() - scrapeStart) / 1000).toFixed(1);

      document.getElementById('progress-bar').style.width = '100%';
      const completionWarnings = data.warnings || warnings;
      const completionNotices = data.notices || notices;
      if (completionNotices.length) {
        collectionNotice.textContent = completionNotices.join('\n');
        collectionNotice.style.display = 'block';
      } else {
        collectionNotice.style.display = 'none';
      }
      if (completionWarnings.length) {
        errorBox.textContent = '주의: ' + completionWarnings.join(' / ');
        errorBox.classList.add('warning');
        errorBox.style.display = 'block';
      } else {
        errorBox.style.display = 'none';
      }
      document.getElementById('status-text').textContent = completionWarnings.length
        ? '분석 완료 · 데이터 주의사항을 확인하세요.'
        : completionNotices.length
          ? '분석 완료 · 이미 수집한 데이터를 사용했습니다.'
          : fromCache ? '수집된 데이터 분석 완료' : '수집·분석 완료!';
      document.getElementById('eta-text').textContent     = '';
      document.getElementById('meta-text').textContent = `총 ${data.analyzed.toLocaleString()}개 분석 완료`;
      const analyzedAt = new Date((data.analyzed_at || Date.now() / 1000) * 1000).toLocaleString('ko-KR', {
        year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Seoul'
      });
      summaryBox.innerHTML = `
        <span class="summary-item">소스 <strong>${SOURCE_LABELS[data.source || selectedSource]}</strong></span>
        <span class="summary-item">분석 공고 <strong>${data.analyzed.toLocaleString()}개</strong></span>
        ${data.deduplicated
          ? `<span class="summary-item">중복 공고 통합 <strong>${data.deduplicated.toLocaleString()}개</strong></span>`
          : ''
        }
        ${completionWarnings.length
          ? `<span class="summary-item">데이터 주의사항 <strong>${completionWarnings.length}건</strong></span>`
          : ''
        }
        ${fromCache
          ? '<span class="summary-item">저장된 데이터로 분석</span>'
          : `<span class="summary-item">소요 시간 <strong>${elapsed}초</strong></span>`
        }
        <span class="summary-item">분석 시각 <strong>${analyzedAt}</strong></span>
      `;
      const collectionTime = timestamp => new Date(timestamp * 1000).toLocaleString('ko-KR', {
        month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Seoul'
      });
      Object.values(data.collection_info || {}).forEach(info => {
        const item = document.createElement('span');
        item.className = 'summary-item';
        item.textContent = info.scope_current
          ? `${info.label}: ${info.jobs.toLocaleString()}개 ${info.partial ? '저장 · 일부 상세 미확보' : '수집 완료'} · ${collectionTime(info.ts)} 수집`
          : `${info.label}: 이전 범위 공고 ${info.jobs.toLocaleString()}개 저장 · ${collectionTime(info.ts)} 수집`;
        if (info.next_refresh_at && info.next_refresh_at * 1000 > Date.now()) {
          item.textContent += ` · ${collectionTime(info.next_refresh_at)}부터 재수집 가능`;
        }
        summaryBox.appendChild(item);
      });
      Object.entries(data.collection_stats || {}).forEach(([source, stats]) => {
        const item = document.createElement('span');
        item.className = 'summary-item';
        item.textContent = `${SOURCE_LABELS[source] || source} 이번 요청: 새 상세 ${stats.succeeded.toLocaleString()}개 · ` +
          `기존 본문 ${stats.reused.toLocaleString()}개 재사용 · 제외 ${stats.skipped.toLocaleString()}개`;
        summaryBox.appendChild(item);
      });
      summaryBox.style.display = 'flex';

      const medalClass = ['gold', 'silver', 'bronze'];
      const maxCount   = data.results[0]?.count || 1;
      const tbody      = document.getElementById('result-body');
      latestResultsByLang = new Map(data.results.map(row => [row.lang, row]));

      data.results.forEach(row => {
        const medal   = row.rank <= 3 ? medalClass[row.rank - 1] : '';
        const barPct  = Math.round(row.count / maxCount * 100);

        const tr = document.createElement('tr');
        tr.dataset.lang = row.lang;
        tr.classList.toggle('selected-lang-row', row.lang === selectedLang);

        const rankCell = document.createElement('td');
        const rankBadge = document.createElement('span');
        rankBadge.className = ['rank-badge', medal].filter(Boolean).join(' ');
        rankBadge.textContent = row.rank;
        rankCell.appendChild(rankBadge);

        const langCell = document.createElement('td');
        langCell.className = 'lang-cell';
        langCell.tabIndex = 0;
        langCell.setAttribute('role', 'button');
        langCell.setAttribute('aria-pressed', String(row.lang === selectedLang));
        langCell.setAttribute('aria-label', `${row.lang} 선택`);

        const langName = document.createElement('span');
        langName.className = 'lang-name';
        langName.textContent = row.lang;
        langCell.appendChild(langName);

        const countCell = document.createElement('td');
        countCell.className = 'count-cell';
        countCell.textContent = row.count.toLocaleString();

        const ratioCell = document.createElement('td');
        const barCell = document.createElement('div');
        barCell.className = 'bar-cell';

        const barWrap = document.createElement('div');
        barWrap.className = 'bar-wrap';

        const bar = document.createElement('div');
        bar.className = ['bar', medal].filter(Boolean).join(' ');
        bar.style.width = `${barPct}%`;
        barWrap.appendChild(bar);

        const pct = document.createElement('span');
        pct.className = 'pct';
        pct.textContent = `${row.ratio}%`;

        barCell.append(barWrap, pct);
        ratioCell.appendChild(barCell);

        tr.append(rankCell, langCell, countCell, ratioCell);
        tbody.appendChild(tr);
      });

      bindLanguageTable(tbody);
      renderLanguageJobs(selectedLang);

      if (data.ts) {
        const timeStr = new Date(data.ts * 1000).toLocaleString('ko-KR', {
          year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Seoul'
        });
        document.getElementById('last-refreshed-time').textContent = timeStr;
        document.getElementById('last-refreshed-label').textContent =
          requestSource === 'all' && Object.keys(data.collection_info || {}).length > 1
            ? '데이터 수집 시각(가장 이전):' : '데이터 수집 시각:';
        document.getElementById('last-refreshed').style.display = 'block';
      }

      if (fromCache) {
        statusBox.style.display = 'none';
      } else {
        document.getElementById('btn-dismiss').style.display = 'block';
      }
      resultBox.style.display = 'block';
      btn.disabled = false;
      setAnalysisFiltersDisabled(false);
      btnRefresh.disabled = false;
      btnRefresh.style.display = 'inline-block';
      btn.classList.remove('loading');
      btnText.textContent = '다시 분석';
      settled = true;
      es.close();
    }

    else if (data.type === 'error') {
      settled = true;
      errorBox.textContent    = '오류: ' + data.msg;
      errorBox.classList.remove('warning');
      errorBox.style.display  = 'block';
      statusBox.style.display = 'none';
      summaryBox.style.display = 'none';
      resultBox.style.display = 'none';
      jobListBox.style.display = 'none';
      btn.disabled = false;
      setAnalysisFiltersDisabled(false);
      btnRefresh.disabled = false;
      btn.classList.remove('loading');
      btnText.textContent = '다시 시도';
      es.close();
    }
  };

  es.onmessage = event => {
    try {
      handleData(JSON.parse(event.data));
    } catch (error) {
      handleData({ type: 'error', msg: `서버 응답을 읽지 못했습니다: ${error.message}` });
    }
  };

  es.onerror = () => {
    if (settled || recovering || requestId !== activeAnalysis) return;
    recovering = true;
    es.close();
    document.getElementById('status-text').textContent =
      '화면 연결이 끊겼습니다. 서버 작업 완료 여부 확인 중...';
    document.getElementById('eta-text').textContent = '';

    const recover = async () => {
      if (settled || requestId !== activeAnalysis) return;
      try {
        const statusParams = new URLSearchParams({
          source: requestSource,
          category: requestCategory
        });
        if (runId) statusParams.set('run_id', runId);
        const response = await fetch(`/scrape-status?${statusParams}`, {
          cache: 'no-store'
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const status = await response.json();
        if (settled || requestId !== activeAnalysis) return;
        if (status.outcome) {
          handleData(status.outcome);
          return;
        }
        if (status.running) {
          document.getElementById('meta-text').textContent =
            `서버에서 계속 분석 중 · 현재 캐시 ${status.jobs.toLocaleString()}개`;
          window.setTimeout(recover, 5000);
          return;
        }
        if (status.available || status.valid) {
          selectSource(requestSource);
          startScrape(false, true);
          return;
        }
        throw new Error('완료된 캐시가 없습니다.');
      } catch (error) {
        handleData({ type: 'error', msg: `연결 복구 실패: ${error.message}` });
      }
    };

    window.setTimeout(recover, 1500);
  };
}
