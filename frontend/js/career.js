const YEAR_LABELS = ['신입','1년','2년','3년','4년','5년','6년','7년','8년','9년','10년 이상'];

let careerMin = 0;
let careerMax = 10;

function yearLabel(v) {
  return YEAR_LABELS[v] ?? `${v}년`;
}

function careerText(min, max) {
  if (min === 0 && max === 10) return '경력 전체';
  if (min === max) return yearLabel(min);
  if (min === 0)  return `${yearLabel(max)} 이하`;
  if (max === 10) return `${yearLabel(min)} 이상`;
  return `${yearLabel(min)} ~ ${yearLabel(max)}`;
}

function updateSliderUI() {
  const minEl = document.getElementById('range-min');
  const maxEl = document.getElementById('range-max');
  const fill  = document.getElementById('range-fill');

  const min = parseInt(minEl.value);
  const max = parseInt(maxEl.value);
  const pct = v => (v / 10) * 100;

  fill.style.left  = pct(min) + '%';
  fill.style.width = (pct(max) - pct(min)) + '%';

  document.getElementById('career-label').textContent = careerText(min, max);
}

function onRangeChange() {
  const minEl = document.getElementById('range-min');
  const maxEl = document.getElementById('range-max');
  let min = parseInt(minEl.value);
  let max = parseInt(maxEl.value);

  if (min > max) {
    if (this === minEl) { minEl.value = max; min = max; }
    else                { maxEl.value = min; max = min; }
  }

  updateSliderUI();
}

function openCareerModal() {
  document.getElementById('range-min').value = careerMin;
  document.getElementById('range-max').value = careerMax;
  updateSliderUI();
  document.getElementById('career-overlay').style.display = 'block';
  document.getElementById('career-modal').style.display   = 'block';
}

function closeCareerModal() {
  document.getElementById('career-overlay').style.display = 'none';
  document.getElementById('career-modal').style.display   = 'none';
}

function resetCareer() {
  document.getElementById('range-min').value = 0;
  document.getElementById('range-max').value = 10;
  updateSliderUI();
}

function applyCareer() {
  careerMin = parseInt(document.getElementById('range-min').value);
  careerMax = parseInt(document.getElementById('range-max').value);

  const text = careerText(careerMin, careerMax);
  document.getElementById('btn-career-text').textContent = text;

  const btn = document.getElementById('btn-career');
  if (careerMin === 0 && careerMax === 10) btn.classList.remove('active');
  else btn.classList.add('active');

  closeCareerModal();
  startScrape(false);
}

function getCareerParams() {
  return { years_min: careerMin, years_max: careerMax };
}
