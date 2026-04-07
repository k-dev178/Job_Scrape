function startScrape() {
  const btn = document.getElementById('btn');
  btn.disabled = true;
  btn.textContent = '분석 중...';

  document.getElementById('status-box').style.display = 'block';
  document.getElementById('result-box').style.display = 'none';
  document.getElementById('error-box').style.display = 'none';
  document.getElementById('result-body').innerHTML = '';
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('eta-text').textContent = '';

  let startTime = null;

  const es = new EventSource('/scrape');

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);

    if (data.type === 'status') {
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
      document.getElementById('meta-text').textContent = `필터 제외: ${data.skipped}개`;

      const elapsed = (Date.now() - startTime) / 1000;
      const rate = data.done / elapsed;
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
      document.getElementById('status-text').textContent = '분석 완료!';
      document.getElementById('eta-text').textContent = '';
      document.getElementById('meta-text').textContent =
        `분석 공고: ${data.analyzed.toLocaleString()}개 · 제외: ${data.skipped}개`;

      const maxCount = data.results[0]?.count || 1;
      const tbody = document.getElementById('result-body');
      data.results.forEach(row => {
        const barWidth = Math.round(row.count / maxCount * 180);
        tbody.innerHTML += `
          <tr>
            <td>${row.rank}</td>
            <td>${row.lang}</td>
            <td>${row.count.toLocaleString()}</td>
            <td>
              <div class="bar-cell">
                <div class="bar" style="width:${barWidth}px"></div>
                <span class="pct">${row.ratio}%</span>
              </div>
            </td>
          </tr>`;
      });

      document.getElementById('result-box').style.display = 'block';
      btn.disabled = false;
      btn.textContent = '다시 스크래핑';
      es.close();
    }

    else if (data.type === 'error') {
      const box = document.getElementById('error-box');
      box.textContent = '오류: ' + data.msg;
      box.style.display = 'block';
      btn.disabled = false;
      btn.textContent = '다시 시도';
      es.close();
    }
  };

  es.onerror = () => {
    es.close();
    btn.disabled = false;
    btn.textContent = '다시 시도';
  };
}
