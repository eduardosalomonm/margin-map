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

function renderScenario() {
  const controls = ['price', 'volume', 'cost'].map(key => document.getElementById(`scenario-${key}`));
  document.querySelectorAll('[data-case-preset]').forEach(button => {
    const preset = decisionPresets[button.dataset.casePreset];
    button.setAttribute('aria-pressed', String(currentPeriod === 'all' && !customRange && !hasFilters() &&
      ['price', 'volume', 'cost'].every((key, index) => controls[index].value !== '' && Number(controls[index].value) === preset[key])));
  });
  if (!controls[0].dataset.ready) {
    controls.forEach(input => input.addEventListener('input', renderScenario));
    controls[0].dataset.ready = 'true';
    document.getElementById('scenario-reset').addEventListener('click', () => {
      controls.forEach(input => { input.value = '0'; }); renderScenario();
    });
  }
  const base = aggregate(periodRows(currentPeriod));
  const result = document.getElementById('scenario-result');
  const decision = document.getElementById('scenario-decision');
  const error = document.getElementById('scenario-error');
  const comparison = document.getElementById('scenario-comparison-chart');
  const coverage = document.getElementById('scenario-coverage');
  const afterLabel = scenarioModel && scenarioModel.incomplete ? 'Known-cost subtotal' : 'After declared variable costs';
  coverage.textContent = scenarioModel && scenarioModel.incomplete
    ? 'Incomplete costs: missing inputs remain excluded. This subtotal cannot establish the full contribution margin. See Input assumptions in Data controls.'
    : scenarioModel ? 'Shipping, fulfilment and fees scale with orders; advertising stays fixed. Overhead is excluded.'
    : 'Product margin only: fulfilment, payment fees, shipping and advertising are not modelled until declared.';
  error.textContent = '';
  if (!base.units) {
    result.textContent = 'No sales in this selection. Change the dates or reset the filters.';
    comparison.innerHTML = '';
    decision.textContent = 'Import sales before modelling a commercial decision.'; return;
  }
  let scenario;
  try {
    scenario = calculateScenario(base, ...controls.map(input => input.value === '' ? NaN : Number(input.value)), scenarioModel);
  } catch (failure) {
    error.textContent = failure.message;
    result.textContent = 'Correct the assumptions to calculate the scenario.';
    comparison.innerHTML = '';
    decision.textContent = ''; return;
  }
  const metrics = [
    ['Sales incl. VAT', base.gross, scenario.gross, euro],
    ['Product cost', base.net - base.margin, scenario.cost, euro],
    ['Units', base.units, scenario.units, number],
    ['Product margin', base.margin, scenario.margin, euro]
  ];
  if (scenarioModel) metrics.push(
    ['Shipping charged ex VAT', base.ship, scenario.ship, euro],
    ['Fulfilment', base.fulfil, scenario.fulfil, euro],
    ['Payment fees', base.fees, scenario.fees, euro],
    ['Advertising · fixed', base.ads, scenario.ads, euro],
    [afterLabel, base.after, scenario.after, euro]
  );
  result.innerHTML = '<table class="scenario-comparison"><thead><tr><th scope="col">Metric</th><th scope="col">Baseline</th><th scope="col">Scenario</th><th scope="col">Change</th></tr></thead><tbody>' +
    metrics.map(([label, before, after, format], index) => `<tr${index === metrics.length - 1 ? ' class="result-row"' : ''}><th scope="row">${label}</th><td>${format(before)}</td><td>${format(after)}</td><td>${format(after - before)}</td></tr>`).join('') + '</tbody></table>';
  const before = scenarioModel ? base.after : base.margin;
  const after = scenarioModel ? scenario.after : scenario.margin;
  const name = scenarioModel ? (scenarioModel.incomplete ? 'known-cost subtotal' : 'result after declared variable costs') : 'product margin';
  const plot = [['Sales incl. VAT', base.gross, scenario.gross], [scenarioModel ? afterLabel : 'Product margin', before, after]];
  comparison.innerHTML = plot.map(([label, baseline, modelled]) => {
    const scale = Math.max(1, Math.abs(baseline), Math.abs(modelled));
    return `<div class="scenario-plot"><h3>${label}</h3>${[['Baseline', baseline], ['Scenario', modelled]].map(([caption, value]) =>
      `<div class="scenario-bar-label"><span>${caption}</span><strong>${euro(value)}</strong></div><div class="scenario-track"><span class="${caption === 'Scenario' ? 'modelled' : ''}${value < 0 ? ' negative' : ''}" style="width:${100 * Math.abs(value) / scale}%"></span></div>`).join('')}</div>`;
  }).join('');
  const needed = scenarioModel ? scenario.requiredAfterVolumeChange : scenario.requiredVolumeChange;
  let verdict = scenario.gross > base.gross && after < before
    ? `Sales rise by ${euro(scenario.gross - base.gross)}, but the ${name} falls by ${euro(before - after)}. More orders do not make this offer better on these assumptions.`
    : `The ${name} changes by ${euro(after - before)}. This is a modelled outcome, not measured demand.`;
  if (needed === null) {
    verdict += after <= 0 ? ' Review price and costs before scaling a loss-making scenario.'
      : ' There is no positive baseline recovery threshold to report.';
  } else {
    verdict += needed >= 0
      ? ` You need ${pct(needed)} more orders at the same basket mix to preserve baseline ${name}.`
      : ` Orders could fall by ${pct(-needed)} before ${name} drops below baseline.`;
  }
  decision.textContent = verdict;
}

function applyDecisionPreset(name) {
  const preset = decisionPresets[name];
  if (!preset) return;
  document.getElementById('reset-view').click();
  for (const key of ['price', 'volume', 'cost']) document.getElementById(`scenario-${key}`).value = String(preset[key]);
  document.querySelectorAll('[data-case-preset]').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.casePreset === name));
  });
  activateTab(tabs.find(button => button.dataset.tab === 'scenario'));
  renderScenario();
  document.getElementById('case-heading').focus();
}

function setupDecisionCase() {
  const entry = document.getElementById('start-decision-case');
  if (!entry) return;
  entry.addEventListener('click', () => applyDecisionPreset('offer'));
  document.querySelectorAll('[data-case-preset]').forEach(button => {
    button.addEventListener('click', () => applyDecisionPreset(button.dataset.casePreset));
  });
  window.addEventListener('hashchange', () => {
    if (window.location.hash === '#decision-case') applyDecisionPreset('offer');
  });
  if (window.location.hash === '#decision-case') applyDecisionPreset('offer');
}

if (typeof module !== 'undefined' && module.exports) module.exports = { calculateScenario, decisionPresets };
