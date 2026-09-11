// Real Chromium microphone capture against the opt-in local Compose test overlay.
// Reports contain identities/counts only; never transcript text, audio or cookies.
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const root = fileURLToPath(new URL('../', import.meta.url));
const base = process.env.TRACK_UI_BASE_URL || 'http://127.0.0.1:8000';
assert(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname), 'Use a loopback stack');
const output = resolve(root, 'test-results/track-ui');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: process.env.HEADED !== 'true', args: [
  '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
  `--use-file-for-fake-audio-capture=${resolve(root, 'tests/data/test_cs.wav')}`,
] });
const context = await browser.newContext({ permissions: ['microphone'], viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const report = { browser: browser.version(), sessions: [], checks: [] };
const check = name => { report.checks.push(name); console.log(`PASS ${name}`); };
const pause = ms => new Promise(done => setTimeout(done, ms));
async function until(read, predicate, label, timeout = 180000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await read();
    if (predicate(value)) return value;
    await pause(1000);
  }
  throw new Error(`Timed out: ${label}`);
}
async function index(id) {
  const response = await context.request.get(`${base}/api/sessions/${id}/tracks`);
  return response.ok() ? response.json() : null;
}
function track(value, stage, id) { return value?.tracks.find(t => t.stage === stage && t.track_id === id); }
async function stagePanel(stage) {
  await page.getByRole('button', { name: stage === 'refined' ? 'Refined real-time' : 'Final transcript', exact: true }).click();
  return page.getByTestId(`${stage}-track-results`);
}
async function settings() {
  await page.getByRole('button', { name: 'Session settings', exact: true }).click();
  await page.getByTestId('refined-track-picker').waitFor();
}
async function rejectSelections(audioUrl) {
  const created = await context.request.post(`${base}/api/sessions`, { data: {} });
  assert.equal(created.status(), 200);
  const { session_id: id } = await created.json();
  const invalid = new URL(audioUrl);
  invalid.protocol = new URL(base).protocol;
  invalid.searchParams.set('session_id', id);
  try {
    for (const selection of ['not-configured', 'shadow', 'whisperx,whisperx', '../private']) {
      invalid.searchParams.set('refinement_tracks', selection);
      const response = await context.request.get(invalid.toString());
      assert.equal(response.status(), 400, 'Invalid selections must fail before audio admission');
    }
    const pending = await index(id);
    assert.deepEqual(pending.tracks, [], 'Rejected selections must not freeze a plan');
  } finally {
    await context.request.post(`${base}/api/sessions/${id}/finish`);
  }
  check('unconfigured, missing-primary, duplicate and malformed IDs rejected before audio');
}
async function record(label, { refined = true, final = true, secondary = false, duration = 12000 } = {}) {
  await page.goto(`${base}/live`);
  await page.getByRole('button', { name: 'Record now', exact: true }).waitFor();
  await page.locator('.dropdown-trigger').first().click();
  await page.getByPlaceholder('Search...', { exact: true }).fill('Czech');
  await page.locator('.dropdown-item').filter({ hasText: 'cs' }).click();
  await settings();
  await page.locator('#sc-out-refined').setChecked(refined);
  await page.locator('#sc-out-final').setChecked(final);
  await page.getByLabel('Recording retention', { exact: true }).selectOption('store');
  if (refined) await page.getByLabel('Refinement window (sec)', { exact: true }).fill('10');
  for (const stage of ['refined', 'final']) {
    const picker = page.getByTestId(`${stage}-track-picker`);
    assert(await picker.getByRole('checkbox', { name: /WhisperX/ }).isChecked());
    assert(await picker.getByRole('checkbox', { name: /WhisperX/ }).isDisabled());
    assert(!await picker.getByRole('checkbox', { name: /Test text only/ }).isChecked(), 'Optional tracks default off');
    if ((stage === 'refined' && refined) || (stage === 'final' && final)) {
      for (const name of ['Test text only', 'Test failure'])
        await picker.getByRole('checkbox', { name: new RegExp(name) }).setChecked(secondary);
    }
  }
  const created = page.waitForResponse(r => r.url().endsWith('/api/sessions') && r.request().method() === 'POST');
  const socket = page.waitForEvent('websocket', { predicate: ws => ws.url().includes('/ws/audio?') });
  await page.getByRole('button', { name: 'Record now', exact: true }).click();
  const { session_id: id } = await (await created).json();
  const audioUrl = new URL((await socket).url());
  const start = Date.now();
  report.sessions.push({ label, id, refined, final, secondary });
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2));
  assert(await page.getByTestId('refined-track-picker').getByRole('checkbox').last().isDisabled());
  if (secondary) {
    assert.equal(audioUrl.searchParams.get('refinement_tracks'), 'whisperx,shadow,failure');
    assert.equal(audioUrl.searchParams.get('final_tracks'), 'whisperx,shadow,failure');
    const panel = await stagePanel('refined');
    await until(() => index(id), value => track(value, 'refined', 'whisperx')?.results.some(r => r.status === 'succeeded'), 'live WhisperX window', 90000);
    await panel.locator('.msg').first().waitFor();
    assert(await page.getByRole('button', { name: /Stop$/ }).isVisible());
    check('real refinement arrives in its tab while recording');
  }
  await pause(Math.max(0, duration - (Date.now() - start)));
  await page.getByRole('button', { name: /Stop$/ }).click();
  check(`${label}: controls frozen and audio stopped`);
  const value = await until(() => index(id), current => {
    if (!current) return false;
    const expected = (Number(refined) + Number(final)) * (secondary ? 3 : 1);
    return current.tracks.length === expected && current.tracks.every(t => t.results.length &&
      t.results.every(r => r.status === (t.track_id === 'failure' ? 'failed' : 'succeeded'))) && (!final || current.has_recording);
  }, `${label} terminal track results`, 240000);
  assert.equal(value.has_recording, final, 'Refinement-only keeps windows, Final keeps playback audio');
  check(`${label}: selected stage outcomes persisted`);
  return { id, value, audioUrl };
}
async function timedPlayback(id, stage) {
  const value = await index(id);
  const selected = track(value, stage, 'whisperx');
  const results = [...selected.results].sort((a, b) => Number(a.unit_id.split(':')[1] || 0) - Number(b.unit_id.split(':')[1] || 0));
  const words = [];
  for (const result of results) {
    const response = await context.request.get(`${base}/api/sessions/${id}/track-results/${result.result_id}`);
    assert.equal(response.status(), 200);
    const payload = await response.json();
    assert(!JSON.stringify(payload).includes('s3://'), 'Read API must not expose object locations');
    words.push(...payload.transcript.segments.flatMap(s => s.words || []));
  }
  assert(words.length > 0, 'Real profile must have word timings for this fixture');
  const panel = await stagePanel(stage);
  await panel.getByRole('tab', { name: 'WhisperX', exact: true }).click();
  await until(() => panel.locator('.word').count(), count => count === words.length, 'all timed words rendered');
  const audio = panel.locator('audio');
  await until(() => audio.evaluate(el => Number.isFinite(el.duration) && el.duration > 0), Boolean, 'audio metadata');
  const candidates = [words.findIndex(w => w.end_s > w.start_s)];
  if (stage === 'refined') candidates.push(words.findIndex(w => w.start_s >= 10 && w.end_s > w.start_s));
  for (const i of candidates) {
    assert(i >= 0, 'Expected timed words across refinement windows');
    const time = (words[i].start_s + words[i].end_s) / 2;
    await audio.evaluate((el, seconds) => { el.pause(); el.currentTime = seconds; }, time);
    await until(() => panel.locator('.word').nth(i).getAttribute('class'), value => value.includes('active'), 'word highlight follows audio');
    await panel.locator('.word').nth(i).click();
    assert(await audio.evaluate(el => !el.paused), 'Clicking a word starts actual playback');
    await audio.evaluate(el => el.pause());
  }
  check(`${stage}: actual audio playback and track-owned word highlighting`);
}
try {
  if (process.env.TRACK_UI_REOPEN_SESSION) {
    const id = process.env.TRACK_UI_REOPEN_SESSION;
    await page.goto(`${base}/recordings/${id}`);
    for (const stage of ['refined', 'final']) {
      const panel = await stagePanel(stage);
      await panel.getByRole('tab', { name: 'Test text only', exact: true }).waitFor();
      await panel.getByRole('tab', { name: 'Test text only', exact: true }).click();
      await panel.getByText('Word timings are unavailable for this output.', { exact: true }).waitFor();
    }
    check('historical labels and results survive current catalog changes');
  } else {
    const main = await record('multiple-tracks', { secondary: true, duration: 18000 });
    await rejectSelections(main.audioUrl);
    for (const stage of ['refined', 'final']) {
      const panel = await stagePanel(stage);
      await panel.getByRole('tab', { name: 'Test failure', exact: true }).click();
      await panel.getByRole('alert').first().waitFor();
      await panel.getByRole('tab', { name: 'Test text only', exact: true }).click();
      await panel.getByText('Word timings are unavailable for this output.', { exact: true }).waitFor();
      assert.equal(await panel.locator('.word').count(), 0);
      await panel.locator('audio').evaluate(async el => { await el.play(); el.pause(); });
      await timedPlayback(main.id, stage);
    }
    check('failures are isolated; text-only tracks retain ordinary playback without fabricated timings');
    assert.deepEqual((await index(main.id)).tracks.map(t => [t.stage, t.track_id, t.primary]), main.value.tracks.map(t => [t.stage, t.track_id, t.primary]));
    await page.getByRole('button', { name: 'New session', exact: true }).click();
    const choice = page.getByTestId('refined-track-picker').getByRole('checkbox', { name: /Test text only/ });
    assert(await choice.isEnabled());
    assert(await choice.isChecked(), 'New session keeps preferences');
    check('New session unlocks choices and keeps preferences');
    await page.goto(`${base}/recordings/${main.id}`);
    await page.reload();
    await timedPlayback(main.id, 'refined');
    await timedPlayback(main.id, 'final');
    check('reload and direct historical link retain selected results and primary identities');
    await page.screenshot({ path: resolve(output, 'results.png'), fullPage: true });
    await record('primary-only', { duration: 12000 });
    await record('refinement-only', { final: false, duration: 12000 });
    await record('final-only', { refined: false, duration: 12000 });
  }
  assert.deepEqual(errors, [], 'No browser runtime errors');
  check('no browser runtime errors');
} catch (error) {
  const stop = page.getByRole('button', { name: /Stop$/ });
  if (await stop.isVisible().catch(() => false)) await stop.click().catch(() => {});
  await page.screenshot({ path: resolve(output, 'failure.png'), fullPage: true }).catch(() => {});
  report.failure = error.message;
  throw error;
} finally {
  await writeFile(resolve(output, process.env.TRACK_UI_REOPEN_SESSION ? 'reopen-report.json' : 'report.json'), JSON.stringify(report, null, 2));
  await browser.close();
}
