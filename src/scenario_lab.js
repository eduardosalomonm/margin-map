const decisionPresets = {
  offer: {price: -20, volume: 30, cost: 0},
  alternative: {price: -10, volume: 20, cost: 0}
};

function calculateScenario(base, priceChange, volumeChange, costChange, variable = null) {
  if (![priceChange, volumeChange, costChange].every(Number.isFinite) ||
      priceChange < -90 || priceChange > 200 || volumeChange < -100 ||
      volumeChange > 500 || costChange < -100 || costChange > 500) {
    throw new Error('Enter price from -90 to 200%, volume and cost from -100 to 500%.');
  }
  const price = 1 + priceChange / 100, volume = 1 + volumeChange / 100;
  const cost = (base.net - base.margin) * (1 + costChange / 100);
  const marginAtBaseVolume = base.net * price - cost;
  const scenario = {
    gross: base.gross * price * volume, net: base.net * price * volume,
    cost: cost * volume, margin: marginAtBaseVolume * volume, units: base.units * volume,
    requiredVolumeChange: base.margin > 0 && marginAtBaseVolume > 0
      ? (base.margin / marginAtBaseVolume - 1) * 100 : null,
    after: null, requiredAfterVolumeChange: null
  };
  if (variable) {
    if (!Number.isFinite(variable.paymentRate) || variable.paymentRate < 0 || variable.paymentRate >= 1) {
      throw new Error('A valid declared payment fee rate is required.');
    }
    const feesAtBaseVolume = Math.max(0, base.fees + base.gross * (price - 1) * variable.paymentRate);
    const contributionAtBaseVolume = marginAtBaseVolume + base.ship - base.fulfil - feesAtBaseVolume;
    Object.assign(scenario, {
      ship: base.ship * volume, fulfil: base.fulfil * volume,
      fees: feesAtBaseVolume * volume, ads: base.ads,
      after: contributionAtBaseVolume * volume - base.ads,
      requiredAfterVolumeChange: base.after > 0 && contributionAtBaseVolume > 0
        ? ((base.after + base.ads) / contributionAtBaseVolume - 1) * 100 : null
    });
  }
  return scenario;
}

function moneyChange(value) {
  const rounded = Math.round(value * 100) / 100;
  return (rounded > 0 ? '+' : '') + euro(rounded === 0 ? 0 : rounded);
}

function renderScenario() {
  const get = id => document.getElementById(id);
  const controls = ['price', 'volume', 'cost'].map(key => get(`scenario-${key}`));
  for (const button of document.querySelectorAll('[data-case-preset]')) {
    const preset = decisionPresets[button.dataset.casePreset];
    button.setAttribute('aria-pressed', String(
      ['price', 'volume', 'cost'].every((key, index) => controls[index].valueAsNumber === preset[key])
    ));
  }
  const reset = get('scenario-reset');
  if (!controls[0].dataset.ready) {
    controls.forEach(input => input.addEventListener('input', renderScenario));
    controls[0].dataset.ready = 'true';
    reset.addEventListener('click', () => {
      controls.forEach(input => { input.value = '0'; });
      renderScenario();
      controls[0].focus();
    });
  }
  reset.disabled = controls.every(input => input.valueAsNumber === 0);

  const base = aggregate(periodRows(currentPeriod));
  const result = get('scenario-result');
  const decision = get('scenario-decision');
  const error = get('scenario-error');
  const comparison = get('scenario-comparison-chart');
  const title = get('scenario-summary-title');
  const coverage = get('scenario-coverage');
  coverage.textContent = scenarioModel && scenarioModel.incomplete
    ? 'Some costs are missing. Review Input assumptions in Data controls before using the subtotal.'
    : scenarioModel ? 'Basket mix and advertising stay fixed. Order growth is a demand assumption.'
    : 'Product margin covers sales less product costs. Declare fulfilment, fees, shipping and ads to model them.';

  function setResultVisibility(visible) {
    for (const id of ['scenario-impact', 'scenario-key-figures', 'scenario-comparison-card', 'scenario-breakdown']) {
      get(id).hidden = !visible;
    }
  }

  function showUnavailable(heading, message) {
    title.textContent = heading;
    decision.textContent = message;
    comparison.replaceChildren();
    result.textContent = message;
    setResultVisibility(false);
  }

  error.textContent = '';
  for (const input of controls) input.removeAttribute('aria-invalid');
  const invalid = controls.filter(input => input.value === '' || !input.validity.valid);
  if (invalid.length) {
    for (const input of invalid) input.setAttribute('aria-invalid', 'true');
    error.textContent = 'Enter price change from −90% to 200%, and order volume and unit cost changes from −100% to 500%.';
    showUnavailable('Check the assumptions', 'Enter valid values to calculate the scenario.');
    return;
  }
  if (!base.units) {
    showUnavailable('No sales in this selection', 'Choose a period or set of filters with recorded sales.');
    return;
  }

  let scenario;
  try {
    scenario = calculateScenario(base, ...controls.map(input => input.valueAsNumber), scenarioModel);
  } catch (failure) {
    error.textContent = failure.message;
    showUnavailable('Scenario unavailable', 'Review the calculation inputs.');
    return;
  }
  setResultVisibility(true);

  const metrics = [
    ['Sales incl. VAT', base.gross, scenario.gross, euro],
    ['Product cost', base.net - base.margin, scenario.cost, euro],
    ['Units', base.units, scenario.units, number],
    ['Product margin', base.margin, scenario.margin, euro],
  ];
  if (scenarioModel) metrics.push(
    ['Shipping charged ex VAT', base.ship, scenario.ship, euro],
    ['Fulfilment', base.fulfil, scenario.fulfil, euro],
    ['Payment fees', base.fees, scenario.fees, euro],
    ['Advertising · fixed', base.ads, scenario.ads, euro],
    [afterCostLabel, base.after, scenario.after, euro],
  );
  result.innerHTML = '<table class="scenario-comparison"><thead><tr><th scope="col">Metric</th><th scope="col">Baseline</th><th scope="col">Scenario</th><th scope="col">Change</th></tr></thead><tbody>'
    + metrics.map(([label, before, after, format], index) => `<tr${index === metrics.length - 1 ? ' class="result-row"' : ''}><th scope="row">${label}</th><td>${format(before)}</td><td>${format(after)}</td><td>${format === euro ? moneyChange(after - before) : number(after - before)}</td></tr>`).join('')
    + '</tbody></table>';

  const before = scenarioModel ? base.after : base.margin;
  const after = scenarioModel ? scenario.after : scenario.margin;
  const metric = scenarioModel ? afterCostLabel : 'Product margin';
  const plot = [['Sales incl. VAT', base.gross, scenario.gross], [metric, before, after]];
  comparison.innerHTML = plot.map(([label, baseline, modelled]) => {
    const scale = Math.max(1, Math.abs(baseline), Math.abs(modelled));
    return `<div class="scenario-plot"><h3>${label}</h3>${[['Baseline', baseline], ['Scenario', modelled]].map(([caption, value]) =>
      `<div class="scenario-bar-label"><span>${caption}</span><strong>${euro(value)}</strong></div><div class="scenario-track" aria-hidden="true"><span class="${caption === 'Scenario' ? 'modelled' : ''}${value < 0 ? ' negative' : ''}" style="width:${100 * Math.abs(value) / scale}%"></span></div>`).join('')}</div>`;
  }).join('');

  const marginDelta = Math.round((after - before) * 100) / 100;
  const salesDelta = Math.round((scenario.gross - base.gross) * 100) / 100;
  const direction = marginDelta < 0 ? 'down' : marginDelta > 0 ? 'up' : 'flat';
  get('scenario-impact-value').textContent = moneyChange(marginDelta);
  get('scenario-impact-label').textContent = scenarioModel
    ? (scenarioModel.incomplete ? 'Change in known-cost subtotal' : 'Margin change after variable costs')
    : 'Change in product margin';
  get('scenario-scenario-total').textContent = euro(after);
  title.closest('.scenario-verdict').dataset.direction = direction;
  const metricName = scenarioModel && scenarioModel.incomplete ? 'Known-cost subtotal' : 'Margin';
  title.textContent = salesDelta > 0 && marginDelta < 0 ? `Sales rise. ${metricName} falls.`
    : `${metricName} ${direction === 'down' ? 'falls' : direction === 'up' ? 'rises' : 'holds'}.`;

  const needed = scenarioModel ? scenario.requiredAfterVolumeChange : scenario.requiredVolumeChange;
  const threshold = needed === null ? null : Math.round(needed * 10) / 10;
  get('scenario-required-volume').textContent = threshold === null ? 'Unavailable'
    : (threshold > 0 ? '+' : '') + pct(threshold === 0 ? 0 : threshold);
  let thresholdNote = before <= 0 ? 'The selected baseline is zero or below.' : 'Extra orders at this price cannot recover the baseline.';
  if (threshold !== null) {
    const gap = Math.round((needed - controls[1].valueAsNumber) * 10) / 10;
    thresholdNote = gap > 0 ? `The order-growth assumption is ${gap.toFixed(1)} percentage points short.`
      : gap < 0 ? `The order-growth assumption is ${Math.abs(gap).toFixed(1)} percentage points above the threshold.`
      : 'The order-growth assumption is at the threshold.';
  }
  const salesNote = salesDelta === 0 ? 'Sales hold steady.'
    : `Sales ${salesDelta > 0 ? 'rise' : 'fall'} by ${euro(Math.abs(salesDelta))}.`;
  decision.textContent = salesNote + ' ' + thresholdNote;
}

function applyDecisionPreset(name, useSamplePeriod = false) {
  const preset = decisionPresets[name];
  if (!preset) return;
  if (useSamplePeriod) {
    document.getElementById('reset-view').click();
    activateTab(tabs.find(button => button.dataset.tab === 'scenario'));
  }
  for (const key of ['price', 'volume', 'cost']) {
    document.getElementById(`scenario-${key}`).value = String(preset[key]);
  }
  renderScenario();
  if (useSamplePeriod) document.getElementById('scenario-summary-title').focus({preventScroll: true});
}

function showSampleImpact() {
  const base = aggregate(daily);
  if (!base.units) return;
  const {price, volume, cost} = decisionPresets.offer;
  const scenario = calculateScenario(base, price, volume, cost, scenarioModel);
  const margin = scenarioModel ? scenario.after - base.after : scenario.margin - base.margin;
  const sales = scenario.gross - base.gross;
  document.getElementById('overview-case-sales').textContent = moneyChange(sales);
  const marginValue = document.getElementById('overview-case-margin');
  marginValue.textContent = moneyChange(margin);
  marginValue.dataset.direction = margin < 0 ? 'down' : margin > 0 ? 'up' : 'flat';
  document.getElementById('overview-case-margin-label').textContent =
    scenarioModel ? (scenarioModel.incomplete ? 'Change in known-cost subtotal' : 'Change after variable costs')
      : 'Change in product margin';
  document.getElementById('overview-case-deltas').hidden = false;
}

function setupDecisionCase() {
  const entry = document.getElementById('start-decision-case');
  if (!entry) return;
  showSampleImpact();
  entry.addEventListener('click', () => {
    applyDecisionPreset('offer', true);
    document.getElementById('scenario-summary-title').scrollIntoView({block: 'nearest'});
  });
  document.querySelectorAll('[data-case-preset]').forEach(button => {
    button.addEventListener('click', () => applyDecisionPreset(button.dataset.casePreset));
  });
  window.addEventListener('hashchange', () => {
    if (window.location.hash === '#decision-case') applyDecisionPreset('offer', true);
  });
  if (window.location.hash === '#decision-case') applyDecisionPreset('offer', true);
}

if (typeof module !== 'undefined' && module.exports) module.exports = { calculateScenario, decisionPresets };
