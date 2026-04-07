function startScrape(refresh = false) {
  const btn      = document.getElementById('btn');
  const btnText  = document.getElementById('btn-text');
  const btnRefresh = document.getElementById('btn-refresh');
  const statusBox  = document.getElementById('status-box');
  const resultBox  = document.getElementById('result-box');
  const errorBox   = document.getElementById('error-box');
  const summaryBox = document.getElementById('summary-box');

  btn.disabled = true;
  btnRefresh.disabled = true;
  btn.classList.add('loading');
  btnText.textContent = '분석 중...';

  statusBox.style.display  = 'block';
  resultBox.style.display  = 'none';
  errorBox.style.display   = 'none';
  summaryBox.style.display = 'none';

  document.getElementById('result-body').innerHTML   = '';
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('eta-text').textContent    = '';
  document.getElementById('meta-text').textContent   = '';

  let startTime = null;
  const scrapeStart = Date.now();

  const { years_min, years_max } = (typeof getCareerParams === 'function') ? getCareerParams() : { years_min: 0, years_max: 10 };
  const params = new URLSearchParams({ years_min, years_max });
  if (refresh) params.set('refresh', 'true');
  const es = new EventSource(`/scrape?${params}`);

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);

    if (data.type === 'cached') {
      const age = Math.round((Date.now() / 1000 - data.ts) / 60);
      document.getElementById('status-text').textContent = `캐시된 데이터 불러오는 중... (${age}분 전 분석)`;
    }

    else if (data.type === 'status') {
      document.getElementById('status-text').textContent = data.msg;
      if (data.total) {
        document.getElementById('meta-text').textContent = `총 ${data.total.toLocaleString()}개 공고`;
      }
    }

    else if (data.type === 'progress') {
      if (!startTime) startTime = Date.now();

      const pct = Math.round(data.done / data.total * 100);
      document.getElementById('progress-bar').style.width = pct + '%';
      document.getElementById('status-text').textContent =
        `상세 분석 중... ${data.done.toLocaleString()} / ${data.total.toLocaleString()} (${pct}%)`;
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

    else if (data.type === 'complete') {
      document.getElementById('progress-bar').style.width = '100%';
      document.getElementById('status-text').textContent  = '분석 완료!';
      document.getElementById('eta-text').textContent     = '';
      document.getElementById('meta-text').textContent = `총 ${data.analyzed.toLocaleString()}개 분석 완료`;

      const elapsed = ((Date.now() - scrapeStart) / 1000).toFixed(1);
      const fromCache = elapsed < 2;
      const refreshedAt = data.ts
        ? new Date(data.ts * 1000).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
        : '';
      summaryBox.innerHTML = `
        <span class="summary-item">분석 공고 <strong>${data.analyzed.toLocaleString()}개</strong></span>
        ${fromCache
          ? `<span class="summary-item">캐시 데이터 · 마지막 분석 <strong>${refreshedAt}</strong></span>`
          : `<span class="summary-item">소요 시간 <strong>${elapsed}초</strong></span><span class="summary-item">분석 시각 <strong>${refreshedAt}</strong></span>`
        }
      `;
      summaryBox.style.display = 'flex';

      const medalClass = ['gold', 'silver', 'bronze'];
      const maxCount   = data.results[0]?.count || 1;
      const tbody      = document.getElementById('result-body');

      data.results.forEach(row => {
        const medal    = row.rank <= 3 ? medalClass[row.rank - 1] : '';
        const barWidth = Math.round(row.count / maxCount * 160);
        tbody.innerHTML += `
          <tr>
            <td><span class="rank-badge ${medal}">${row.rank}</span></td>
            <td><span class="lang-name">${row.lang}</span></td>
            <td class="count-cell">${row.count.toLocaleString()}</td>
            <td>
              <div class="bar-cell">
                <div class="bar ${medal}" style="width:${barWidth}px"></div>
                <span class="pct">${row.ratio}%</span>
              </div>
            </td>
          </tr>`;
      });

      if (data.ts) {
        const timeStr = new Date(data.ts * 1000).toLocaleString('ko-KR', {
          month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
        });
        document.getElementById('last-refreshed-time').textContent = timeStr;
        document.getElementById('last-refreshed').style.display = 'block';
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
