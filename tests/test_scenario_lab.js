// Run with: node --test tests/test_scenario_lab.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { calculateScenario, decisionPresets } = require('../src/scenario_lab.js');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const base = { gross: 1210, net: 1000, margin: 400, units: 100 };
test('neutral assumptions preserve the baseline', () => {
  const result = calculateScenario(base, 0, 0, 0);
  assert.equal(result.margin, base.margin);
  assert.equal(result.gross, base.gross);
  assert.equal(result.requiredVolumeChange, 0);
});
test('discounting requires enough volume to recover lost margin', () => {
  const result = calculateScenario(base, -10, 0, 0);
  assert.equal(result.margin, 300);
  assert.ok(Math.abs(result.requiredVolumeChange - 100 / 3) < 1e-8);
  assert.ok(Math.abs(calculateScenario(base, -10, result.requiredVolumeChange, 0).margin - 400) < 1e-8);
});
test('price, volume and supplier cost changes combine', () => {
  const result = calculateScenario(base, 10, 20, 10);
  assert.equal(result.gross, 1597.2);
  assert.equal(result.units, 120);
  assert.equal(result.cost, 792);
  assert.equal(result.margin, 528);
});
test('zero sales, losses and nonpositive baselines do not invent recovery ratios', () => {
  assert.equal(calculateScenario(base, 0, -100, 0).margin, 0);
  assert.equal(calculateScenario(base, -90, 0, 0).requiredVolumeChange, null);
  assert.equal(calculateScenario({...base, margin: -100}, 0, 0, 0).requiredVolumeChange, null);
  assert.equal(calculateScenario({gross:0, net:0, margin:0, units:0}, 0, 0, 0).margin, 0);
});
test('invalid and out-of-range assumptions are rejected', () => {
  for (const values of [[NaN,0,0], [Infinity,0,0], [-91,0,0], [201,0,0], [0,-101,0], [0,501,0], [0,0,-101], [0,0,501]]) {
    assert.throws(() => calculateScenario(base, ...values));
  }
});

const trading = {gross: 1210, net: 1000, margin: 400, units: 100,
  ship: 40, fulfil: 100, fees: 30, ads: 50, after: 260};
const variable = {paymentRate: 0.02};
test('variable costs preserve baseline and scale by their declared drivers', () => {
  const neutral = calculateScenario(trading, 0, 0, 0, variable);
  assert.equal(neutral.after, trading.after);
  assert.equal(neutral.requiredAfterVolumeChange, 0);
  const result = calculateScenario(trading, -10, 20, 0, variable);
  assert.equal(result.ship, 48);
  assert.equal(result.fulfil, 120);
  assert.equal(result.ads, 50);
  assert.ok(Math.abs(result.fees - (30 - 121 * 0.02) * 1.2) < 1e-8);
  assert.ok(Math.abs(result.after - (result.margin + result.ship - result.fulfil - result.fees - result.ads)) < 1e-8);
  const recovered = calculateScenario(trading, -10, result.requiredAfterVolumeChange, 0, variable);
  assert.ok(Math.abs(recovered.after - trading.after) < 1e-8);
});
test('zero orders still spend the fixed advertising budget', () => {
  const result = calculateScenario(trading, 0, -100, 0, variable);
  assert.equal(result.after, -50);
  assert.equal(result.fees, 0);
  assert.equal(calculateScenario(trading, -90, 0, 0, variable).requiredAfterVolumeChange, null);
  assert.equal(calculateScenario({...trading, after: -1}, 0, 0, 0, variable).requiredAfterVolumeChange, null);
});
test('no declared model does not invent after-cost results', () => {
  assert.equal(calculateScenario(trading, 0, 0, 0).after, null);
  assert.throws(() => calculateScenario(trading, 0, 0, 0, {paymentRate: NaN}));
});

test('portfolio decisions reconcile with the generated sample dashboard', () => {
  const page = readFileSync(join(__dirname, '../docs/index.html'), 'utf8');
  const rows = JSON.parse(page.match(/const daily=(.*?),allProducts=/)[1]);
  const model = JSON.parse(page.match(/scenarioModel=(.*?),costBasis=/)[1]);
  const baseline = Object.fromEntries(['gross','net','margin','units','ship','fulfil','fees','ads','after']
    .map(key => [key, rows.reduce((total, row) => total + (row[key] || 0), 0)]));
  const scenario = name => {
    const preset = decisionPresets[name];
    return calculateScenario(baseline, preset.price, preset.volume, preset.cost, model);
  };
  const offer = scenario('offer'), alternative = scenario('alternative');
  const cents = value => Math.round(value * 100);
  assert.equal(cents(baseline.after), 3516691);
  assert.equal(cents(offer.gross), 8710565);
  assert.equal(cents(offer.after), 3164584);
  assert.equal(cents(alternative.after), 3644420);
  assert.ok(offer.gross > baseline.gross && offer.after < baseline.after);
  assert.ok(alternative.after > baseline.after);
  assert.equal(offer.requiredAfterVolumeChange.toFixed(1), '40.5');
  assert.equal(alternative.requiredAfterVolumeChange.toFixed(1), '16.8');
  assert.equal(cents(calculateScenario(baseline, -20, offer.requiredAfterVolumeChange, 0, model).after), cents(baseline.after));
  const story = readFileSync(join(__dirname, '../CASE_STUDY.md'), 'utf8');
  for (const value of [baseline.after, offer.after, alternative.after]) {
    assert.ok(story.includes(new Intl.NumberFormat('en-IE', {style:'currency',currency:'EUR'}).format(value)));
  }
});
