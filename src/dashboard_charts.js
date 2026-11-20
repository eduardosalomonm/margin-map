// Calendar buckets keep quiet trading periods visible instead of joining over them.
function salesSeries(rows, period, bounds) {
  if (!rows.length) return [];
  const monthly = period === 'all';
  const dates = rows.map(row => row.date).sort();
  const first = bounds ? bounds.start : dates[0], last = bounds ? bounds.end : dates[dates.length - 1];
  const start = monthly ? `${first.slice(0, 7)}-01` : first;
  const end = monthly ? `${last.slice(0, 7)}-01` : last;
  const buckets = new Map();
  const cursor = new Date(`${start}T00:00:00Z`);
  while (cursor.toISOString().slice(0, 10) <= end) {
    const key = cursor.toISOString().slice(0, monthly ? 7 : 10);
    buckets.set(key, {key, gross: 0, margin: 0, after: 0,
      label: cursor.toLocaleDateString('en-GB', monthly
        ? {month: 'short', year: '2-digit', timeZone: 'UTC'}
        : {day: 'numeric', month: 'short', timeZone: 'UTC'})});
    if (monthly) cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    else cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  rows.forEach(row => {
    const bucket = buckets.get(row.date.slice(0, monthly ? 7 : 10));
    if (!bucket) return;
    for (const key of ['gross', 'margin', 'after']) bucket[key] += row[key] || 0;
  });
  return [...buckets.values()];
}

function drawChart(id, series) {
  const svg = document.getElementById(id);
  if (!svg) return;
  if (svg.clientWidth === 0) return;
  const width = svg.clientWidth || 760;
  const height = svg.clientHeight || 250;
  const labelSize = typeof getComputedStyle === 'function'
    ? .75 * parseFloat(getComputedStyle(document.documentElement).fontSize) : 12;
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', series.length
    ? 'Sales and margin trend. View the values below the chart.' : 'No sales in this view');
  if (!series.length) {
    svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" text-anchor="middle" font-size="${labelSize}">No sales in this view</text>`;
    return;
  }
  const keys = hasVariable ? ['gross', 'margin', 'after'] : ['gross', 'margin'];
  const values = series.flatMap(row => keys.map(key => row[key] || 0));
  const high = Math.max(1, ...values), low = Math.min(0, ...values);
  const padding = (high - low) * 0.08;
  const max = high + padding, min = low < 0 ? low - padding : 0;
  const left = labelSize * 4.7, right = width - labelSize, top = labelSize * 1.7, bottom = height - labelSize * 3.25;
  const x = index => series.length === 1 ? (left + right) / 2
    : left + index * (right - left) / (series.length - 1);
  const y = value => bottom - (value - min) * (bottom - top) / (max - min);
  const ticks = Array.from({length: 5}, (_, i) => min + (max - min) * i / 4);
  if (min < 0) ticks.push(0);
  let markup = ticks.map(value => `<line x1="${left}" y1="${y(value)}" x2="${right}" y2="${y(value)}" class="${value === 0 ? 'chart-zero' : 'chart-grid'}"/><text x="${left - 7}" y="${y(value) + labelSize / 3}" text-anchor="end" font-size="${labelSize}">${esc(new Intl.NumberFormat('en-GB', {notation:'compact',maximumFractionDigits:1}).format(value))}</text>`).join('');
  const colours = {gross: 'var(--accent)', margin: 'var(--teal)', after: 'var(--warn)'};
  const names = {gross: 'Sales incl. VAT', margin: 'Product margin', after: typeof afterCostLabel === 'string' ? afterCostLabel : 'After variable costs'};
  for (const key of keys) {
    const path = series.map((row, i) => `${i ? 'L' : 'M'}${x(i)},${y(row[key] || 0)}`).join(' ');
    markup += `<path d="${path}" fill="none" stroke="${colours[key]}" stroke-width="2.5"${key === 'after' ? ' stroke-dasharray="6 4"' : ''}/>`;
    markup += series.map((row, i) => `<circle cx="${x(i)}" cy="${y(row[key] || 0)}" r="${series.length > 60 ? 2 : 3.5}" fill="${colours[key]}"><title>${esc(`${row.label}: ${names[key]} ${euro(row[key] || 0)}`)}</title></circle>`).join('');
  }
  const labelCount = Math.max(2, Math.min(7, Math.floor((right - left) / (labelSize * 5.8)) + 1));
  const step = Math.max(1, Math.ceil((series.length - 1) / (labelCount - 1)));
  const last = series.length - 1;
  markup += series.map((row, i) => {
    if (i !== last && (i % step || (i > 0 && last - i < step / 2))) return '';
    const anchor = i === last && last > 0 ? 'end' : i === 0 && last > 0 ? 'start' : 'middle';
    return `<text x="${x(i)}" y="${bottom + labelSize * 1.65}" text-anchor="${anchor}" font-size="${labelSize}">${esc(row.label)}</text>`;
  }).join('');
  svg.innerHTML = markup;
}

if (typeof module !== 'undefined' && module.exports) module.exports = {salesSeries};
