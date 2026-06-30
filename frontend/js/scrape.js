let selectedLang = null;
let latestResultsByLang = new Map();
let selectedSource = 'all';

const SOURCE_LABELS = {
  all: '전체',
  wanted: 'Wanted',
  jobkorea: '잡코리아'
};

const SOURCE_DESCRIPTIONS = {
  all: 'Wanted와 잡코리아 백엔드 공고를 통합 분석',
  wanted: '데이터·AI·인프라 공고 제외 — 백엔드 공고만 실시간 분석',
  jobkorea: '전국 · 백엔드개발자 전체 공고를 분석하고 캐시에서 빠르게 조회'
};

function selectSource(source) {
  selectedSource = source;
  selectedLang = null;

  document.querySelectorAll('.source-option').forEach(option => {
    const active = option.dataset.source === source;
    option.classList.toggle('active', active);
    option.setAttribute('aria-pressed', String(active));
  });

  document.getElementById('source-description').textContent = SOURCE_DESCRIPTIONS[source];

  closeJobList();
}

function formatCareerRange(job) {
  const from = Number(job.annual_from || 0);
  const to = Number(job.annual_to ?? 10);

  if (from <= 0 && to >= 100) return '경력 전체';
  if (from <= 0) return `${to}년 이하`;
  if (to >= 100) return `${from}년 이상`;
  if (from === to) return `${from}년`;
  return `${from}년 ~ ${to}년`;
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
      meta.textContent = [job.company, formatCareerRange(job)].filter(Boolean).join(' · ');

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

function startScrape(refresh = false) {
  const btn      = document.getElementById('btn');
  const btnText  = document.getElementById('btn-text');
  const btnRefresh = document.getElementById('btn-refresh');
  const statusBox  = document.getElementById('status-box');
  const resultBox  = document.getElementById('result-box');
  const errorBox   = document.getElementById('error-box');
  const summaryBox = document.getElementById('summary-box');
  const jobListBox = document.getElementById('job-list-box');

  btn.disabled = true;
  btnRefresh.disabled = true;
  btn.classList.add('loading');
  btnText.textContent = '분석 중...';

  statusBox.style.display  = 'block';
  resultBox.style.display  = 'none';
  errorBox.style.display   = 'none';
  errorBox.classList.remove('warning');
  summaryBox.style.display = 'none';
  jobListBox.style.display = 'none';

  document.getElementById('result-body').innerHTML    = '';
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('eta-text').textContent     = '';
  document.getElementById('meta-text').textContent    = '';
  document.getElementById('btn-dismiss').style.display = 'none';

  let startTime = null;
  let progressSource = null;
  const warnings = [];
  const scrapeStart = Date.now();

  const { years_min, years_max } = (typeof getCareerParams === 'function') ? getCareerParams() : { years_min: 0, years_max: 10 };
  const params = new URLSearchParams({ years_min, years_max, source: selectedSource });
  if (refresh) params.set('refresh', 'true');
  const es = new EventSource(`/scrape?${params}`);

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);

    if (data.type === 'cached') {
      const age = Math.round((Date.now() / 1000 - data.ts) / 60);
      document.getElementById('status-text').textContent = `${SOURCE_LABELS[selectedSource]} 캐시된 데이터 불러오는 중... (${age}분 전 분석)`;
    }

    else if (data.type === 'status') {
      document.getElementById('status-text').textContent = data.msg;
      if (data.total) {
        startTime = null;
        progressSource = null;
        document.getElementById('progress-bar').style.width = '0%';
        document.getElementById('meta-text').textContent = `총 ${data.total.toLocaleString()}개 공고`;
      }
    }

    else if (data.type === 'progress') {
      if (!startTime || progressSource !== data.source) {
        startTime = Date.now();
        progressSource = data.source;
      }

      const pct = Math.round(data.done / data.total * 100);
      document.getElementById('progress-bar').style.width = pct + '%';
      document.getElementById('status-text').textContent =
        `${data.source_label ? data.source_label + ' ' : ''}상세 분석 중... ${data.done.toLocaleString()} / ${data.total.toLocaleString()} (${pct}%)`;
      document.getElementById('meta-text').textContent =
        `${data.done.toLocaleString()} / ${data.total.toLocaleString()}개`;

      const elapsed   = (Date.now() - startTime) / 1000;
      const rate      = data.done / elapsed;
      const remaining = Math.round((data.total - data.done) / rate);
      if (remaining > 0 && isFinite(remaining)) {
        const m = Math.floor(remaining / 60);
        const s = remaining % 60;
        document.getElementById('eta-text').textContent =
          m > 0 ? `약 ${m}분 ${s}초 남음` : `약 ${s}초 남음`;
      }
    }

    else if (data.type === 'warning') {
      warnings.push(data.msg);
      errorBox.textContent = '주의: ' + warnings.join(' / ');
      errorBox.classList.add('warning');
      errorBox.style.display = 'block';
    }

    else if (data.type === 'complete') {
      const elapsed = ((Date.now() - scrapeStart) / 1000).toFixed(1);
      const fromCache = elapsed < 2;

      document.getElementById('progress-bar').style.width = '100%';
      const completionWarnings = data.warnings || warnings;
      document.getElementById('status-text').textContent = completionWarnings.length
        ? '일부 사이트는 기존 캐시로 대체했습니다.'
        : '새로고침 완료!';
      document.getElementById('eta-text').textContent     = '';
      document.getElementById('meta-text').textContent = `총 ${data.analyzed.toLocaleString()}개 분석 완료`;
      const refreshedAt = data.ts
        ? new Date(data.ts * 1000).toLocaleString('ko-KR', { year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
        : '';
      summaryBox.innerHTML = `
        <span class="summary-item">소스 <strong>${SOURCE_LABELS[data.source || selectedSource]}</strong></span>
        <span class="summary-item">분석 공고 <strong>${data.analyzed.toLocaleString()}개</strong></span>
        ${completionWarnings.length
          ? `<span class="summary-item">캐시 대체 <strong>${completionWarnings.length}개 사이트</strong></span>`
          : ''
        }
        ${fromCache
          ? `<span class="summary-item">캐시 데이터 · 마지막 분석 <strong>${refreshedAt}</strong></span>`
          : `<span class="summary-item">소요 시간 <strong>${elapsed}초</strong></span><span class="summary-item">분석 시각 <strong>${refreshedAt}</strong></span>`
        }
      `;
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
          year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
        document.getElementById('last-refreshed-time').textContent = timeStr;
        document.getElementById('last-refreshed').style.display = 'block';
      }

      if (fromCache) {
        statusBox.style.display = 'none';
      } else {
        document.getElementById('btn-dismiss').style.display = 'block';
      }
      resultBox.style.display = 'block';
      btn.disabled = false;
      btnRefresh.disabled = false;
      btnRefresh.style.display = 'inline-block';
      btn.classList.remove('loading');
      btnText.textContent = '다시 분석';
      es.close();
    }

    else if (data.type === 'error') {
      errorBox.textContent    = '오류: ' + data.msg;
      errorBox.classList.remove('warning');
      errorBox.style.display  = 'block';
      statusBox.style.display = 'none';
      btn.disabled = false;
      btnRefresh.disabled = false;
      btn.classList.remove('loading');
      btnText.textContent = '다시 시도';
      es.close();
    }
  };

  es.onerror = () => {
    es.close();
    btn.disabled = false;
    btnRefresh.disabled = false;
    btn.classList.remove('loading');
    btnText.textContent = '다시 시도';
  };
}
