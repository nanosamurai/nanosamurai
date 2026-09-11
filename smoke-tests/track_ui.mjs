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
async function stagePanel(stage, displayName = 'WhisperX') {
  if (new URL(page.url()).pathname.startsWith('/recordings/')) {
    const label = `${stage === 'refined' ? 'Refined' : 'Final'} Transcript (${displayName})`;
    await page.getByRole('tab', { name: label, exact: true }).click();
    assert.equal(await page.getByRole('tablist', { name: 'Session transcripts' }).count(), 1);
    assert.equal(await page.getByRole('tabpanel').getByRole('tablist').count(), 0, 'History has one level of transcript tabs');
    return page.getByTestId('track-result-panel');
  }
  await page.getByRole('button', { name: stage === 'refined' ? 'Refined real-time' : 'Final transcript', exact: true }).click();
  const panel = page.getByTestId(`${stage}-track-results`);
  await panel.getByRole('tab', { name: displayName, exact: true }).click();
  return panel;
}
async function settings() {
  await page.getByRole('button', { name: 'Session settings', exact: true }).click();
  await page.getByRole('region', { name: 'Session settings', exact: true }).waitFor();
}
async function settingsStage(stage) {
  const region = page.getByRole('region', { name: 'Session settings', exact: true });
  await region.getByRole('tab', { name: new RegExp(`^${stage === 'refined' ? 'Refined' : 'Final'} `) }).click();
  return page.getByTestId(`${stage}-track-picker`);
}
async function checkSettings() {
  await page.goto(`${base}/live`);
  await settings();
  const region = page.getByRole('region', { name: 'Session settings', exact: true });
  await region.getByText(/Maximum inference input: 30 sec/).waitFor();
  const refinedToggle = region.getByRole('checkbox', { name: 'Enable Refined', exact: true });
  await refinedToggle.uncheck();
  assert.match(await region.getByRole('tab', { selected: true }).innerText(), /^Real-time/);
  await refinedToggle.check();
  const picker = await settingsStage('refined');
  await picker.getByRole('checkbox', { name: /Test text only/ }).check();
  await refinedToggle.uncheck();
  assert.equal(await picker.getByRole('checkbox', { checked: true }).count(), 0);
  await refinedToggle.check();
  assert(await picker.getByRole('checkbox', { name: /Test text only/ }).isChecked());
  await picker.getByRole('checkbox', { name: /WhisperX/ }).uncheck();
  await picker.getByRole('checkbox', { name: /Test text only/ }).uncheck();
  assert(!await refinedToggle.isChecked(), 'Clearing the final selection disables the stage');
  await picker.getByRole('checkbox', { name: /Test text only/ }).check();
  assert(await refinedToggle.isChecked(), 'Selecting while off enables the stage');
  assert(!await picker.getByRole('checkbox', { name: /WhisperX/ }).isChecked(), 'No required primary choice');
  await region.getByRole('tab', { name: 'Recording', exact: true }).click();
  assert.equal(await region.getByLabel('Recording retention', { exact: true }).inputValue(), 'store');
  check('header toggles, remembered selections, empty-stage disablement, optional primary and Recording tab');
}
async function rejectSelections(audioUrl) {
  const created = await context.request.post(`${base}/api/sessions`, { data: {} });
  assert.equal(created.status(), 200);
  const { session_id: id } = await created.json();
  const invalid = new URL(audioUrl);
  invalid.protocol = new URL(base).protocol;
  invalid.searchParams.set('session_id', id);
  try {
    for (const selection of ['not-configured', 'whisperx,whisperx', '../private']) {
      invalid.searchParams.set('refinement_tracks', selection);
      const response = await context.request.get(invalid.toString());
      assert.equal(response.status(), 400, 'Invalid selections must fail before audio admission');
    }
    const pending = await index(id);
    assert.deepEqual(pending.tracks, [], 'Rejected selections must not freeze a plan');
  } finally {
    await context.request.post(`${base}/api/sessions/${id}/finish`);
  }
  check('unconfigured, duplicate and malformed IDs rejected before audio');
}
async function record(label, { refined = true, final = true, secondary = false, secondaryOnly = false, duration = 12000 } = {}) {
  await page.goto(`${base}/live`);
  await page.getByRole('button', { name: 'Record now', exact: true }).waitFor();
  await page.locator('.dropdown-trigger').first().click();
  await page.getByPlaceholder('Search...', { exact: true }).fill('Czech');
  await page.locator('.dropdown-item').filter({ hasText: 'cs' }).click();
  await settings();
  const region = page.getByRole('region', { name: 'Session settings', exact: true });
  await region.getByRole('checkbox', { name: 'Enable Real-time', exact: true }).uncheck();
  await region.getByRole('checkbox', { name: 'Enable Refined', exact: true }).setChecked(refined);
  await region.getByRole('checkbox', { name: 'Enable Final', exact: true }).setChecked(final);
  const selectedIds = secondaryOnly ? ['shadow'] : secondary ? ['whisperx', 'shadow', 'failure'] : ['whisperx'];
  for (const stage of ['refined', 'final']) {
    const picker = await settingsStage(stage);
    const enabled = stage === 'refined' ? refined : final;
    assert(await picker.getByRole('checkbox', { name: /WhisperX/ }).isEnabled());
    assert.equal(await picker.getByRole('checkbox', { name: /WhisperX/ }).isChecked(), enabled);
    assert(!await picker.getByRole('checkbox', { name: /Test text only/ }).isChecked(), 'Optional tracks default off');
    if (enabled) {
      for (const [id, name] of [['shadow', 'Test text only'], ['failure', 'Test failure'], ['whisperx', 'WhisperX']])
        await picker.getByRole('checkbox', { name: new RegExp(name) }).setChecked(selectedIds.includes(id));
      if (stage === 'refined') await page.getByLabel('Refinement window (sec)', { exact: true }).fill('10');
    }
  }
  await region.getByRole('tab', { name: 'Recording', exact: true }).click();
  assert.equal(await region.getByLabel('Recording retention', { exact: true }).inputValue(), 'store');
  const created = page.waitForResponse(r => r.url().endsWith('/api/sessions') && r.request().method() === 'POST');
  const socket = page.waitForEvent('websocket', { predicate: ws => ws.url().includes('/ws/audio?') });
  await page.getByRole('button', { name: 'Record now', exact: true }).click();
  const { session_id: id } = await (await created).json();
  const audioUrl = new URL((await socket).url());
  const start = Date.now();
  report.sessions.push({ label, id, refined, final, secondary, track_ids: selectedIds });
  await writeFile(resolve(output, 'report.json'), JSON.stringify(report, null, 2));
  assert(await region.getByRole('checkbox', { name: 'Enable Refined', exact: true }).isDisabled());
  const frozenPicker = await settingsStage('refined');
  assert(await frozenPicker.getByRole('checkbox').last().isDisabled());
  for (const [stage, parameter] of [['refined', 'refinement_tracks'], ['final', 'final_tracks']]) {
    assert.equal(audioUrl.searchParams.get(stage), String(stage === 'refined' ? refined : final));
    if (!(stage === 'refined' ? refined : final)) assert.equal(audioUrl.searchParams.get(parameter), null);
    if (secondaryOnly) assert.equal(audioUrl.searchParams.get(parameter), 'shadow');
  }
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
    const expected = (Number(refined) + Number(final)) * selectedIds.length;
    return current.tracks.length === expected && current.tracks.every(t => t.results.length &&
      t.results.every(r => r.status === (t.track_id === 'failure' ? 'failed' : 'succeeded'))) && (!final || current.has_recording);
  }, `${label} terminal track results`, 240000);
  assert.equal(value.has_recording, final, 'Refinement-only keeps windows, Final keeps playback audio');
  if (secondaryOnly) assert(value.tracks.every(t => t.track_id === 'shadow' && t.primary), 'Selected alternative becomes the compatibility output');
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
  await until(async () => {
    try { return (await context.request.get(`${base}/api/me`, { timeout: 3000 })).ok(); }
    catch { return false; }
  }, Boolean, 'BFF ready after Compose startup', 60000);
  if (process.env.TRACK_UI_REOPEN_SESSION) {
    const id = process.env.TRACK_UI_REOPEN_SESSION;
    await page.goto(`${base}/recordings/${id}`);
    for (const stage of ['refined', 'final']) {
      const panel = await stagePanel(stage, 'Test text only');
      await panel.getByText('Word timings are unavailable for this output.', { exact: true }).waitFor();
    }
    check('historical labels and results survive current catalog changes');
  } else {
    await checkSettings();
    const main = await record('multiple-tracks', { secondary: true, duration: 18000 });
    await rejectSelections(main.audioUrl);
    for (const stage of ['refined', 'final']) {
      const failurePanel = await stagePanel(stage, 'Test failure');
      await failurePanel.getByRole('alert').first().waitFor();
      const panel = await stagePanel(stage, 'Test text only');
      await panel.getByText('Word timings are unavailable for this output.', { exact: true }).waitFor();
      assert.equal(await panel.locator('.word').count(), 0);
      await panel.locator('audio').evaluate(async el => { await el.play(); el.pause(); });
      await timedPlayback(main.id, stage);
    }
    check('failures are isolated; text-only tracks retain ordinary playback without fabricated timings');
    assert.deepEqual((await index(main.id)).tracks.map(t => [t.stage, t.track_id, t.primary]), main.value.tracks.map(t => [t.stage, t.track_id, t.primary]));
    await page.getByRole('button', { name: 'New session', exact: true }).click();
    await settingsStage('refined');
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
    await record('default-track-only', { duration: 12000 });
    await record('refinement-only', { final: false, duration: 12000 });
    await record('final-only', { refined: false, duration: 12000 });
    await record('alternative-track-only', { secondaryOnly: true, duration: 12000 });
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
