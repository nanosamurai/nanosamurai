/** Browser qualification against the original local Compose stack; no browser mocks. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.BFF_URL || 'http://127.0.0.1:8000';
assert.ok(['localhost', '127.0.0.1'].includes(new URL(base).hostname), 'Use loopback only');
const evidenceDir = path.resolve(process.env.TRACK_UI_EVIDENCE || '.tmp/track-ui');
fs.mkdirSync(evidenceDir, { recursive: true });
const evidenceFile = path.join(evidenceDir, 'sessions.json');
const sessions = [];

async function waitFor(fn, label, timeout = 240000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await fn();
    if (value) return value;
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  throw new Error(`Timed out: ${label}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true, args: [
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
    `--use-file-for-fake-audio-capture=${path.resolve('tests/data/test_cs.wav')}`,
  ] });
  try {
    const context = await browser.newContext({ permissions: ['microphone'], viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const detail = async id => (await context.request.get(`${base}/api/recordings/${id}`)).json();
    await waitFor(async () => {
      try { return (await context.request.get(`${base}/ready`)).ok(); }
      catch { return false; }
    }, 'BFF ready', 60000);
    await page.goto(`${base}/live`);
    const metadata = await (await context.request.get(`${base}/api/me`)).json();
    assert.ok(metadata.async_tracks.length >= 2);

    if (process.argv.includes('--verify-labels')) {
      const saved = JSON.parse(fs.readFileSync(evidenceFile));
      const first = saved[0];
      assert.equal(metadata.async_tracks.find(t => t.stage === 'final' && t.track_id === 'ui-shadow').display_name, 'Renamed test');
      await page.goto(`${base}/recordings/${first.id}?reload=1`);
      await page.getByRole('tab', { name: 'Final Transcript (Test-only text)', exact: true }).waitFor();
      assert.equal((await detail(first.id)).session.stream_controls.track_labels.final['ui-shadow'], 'Test-only text');
      console.log('PASS historical labels survive deployment rename and direct-link reload');
      return;
    }

    const settings = async () => {
      if (!(await page.getByRole('region', { name: 'Session settings', exact: true }).isVisible()))
        await page.getByRole('button', { name: 'Session settings', exact: true }).click();
    };
    const stage = async (name, enabled, labels) => {
      await settings();
      await page.getByRole('checkbox', { name: `Enable ${name}`, exact: true }).setChecked(enabled);
      await page.getByRole('tab', { name: new RegExp(`^${name}`) }).click();
      if (labels) {
        const prefix = name === 'Real-time' ? 'Realtime' : name;
        const picker = page.getByTestId(`${prefix.toLowerCase()}-track-picker`);
        const choices = picker.getByRole('checkbox');
        for (let i = 0; i < await choices.count(); i++) {
          const checkbox = choices.nth(i);
          const label = (await checkbox.getAttribute('aria-label')).split(': ')[1];
          await checkbox.setChecked(labels.includes(label));
        }
      }
    };
    const start = async label => {
      await page.getByRole('region', { name: 'Session settings', exact: true }).getByRole('button', { name: 'Close', exact: true }).click();
      const request = page.waitForRequest(r => r.url().endsWith('/api/sessions') && r.method() === 'POST');
      await page.getByRole('button', { name: 'Record now', exact: true }).click();
      const response = await (await request).response();
      const id = (await response.json()).session_id;
      assert.ok(id);
      sessions.push({ label, id });
      fs.writeFileSync(evidenceFile, JSON.stringify(sessions, null, 2));
      await page.getByRole('button', { name: /Stop/ }).waitFor();
      await waitFor(async () => (await detail(id)).session.stream_controls, 'audio admission', 45000);
      await settings();
      assert.ok(await page.getByRole('checkbox', { name: 'Enable Final', exact: true }).isDisabled());
      return id;
    };
    const stop = async () => {
      await page.getByRole('button', { name: /Stop/ }).click();
      await page.getByRole('button', { name: 'New session', exact: true }).waitFor();
    };
    const fresh = async () => {
      await page.goto(`${base}/live`);
      await page.getByRole('button', { name: 'Session settings', exact: true }).waitFor();
      await settings();
    };

    await settings();
    await page.getByRole('tab', { name: /^Real-time/ }).click();
    assert.equal(await page.getByRole('spinbutton', { name: 'Window (sec)', exact: true }).inputValue(), '');
    if (metadata.realtime_track_capabilities.some(c => c.windowed_realtime && c.maximum_audio_seconds > 0))
      await page.getByText(/Maximum inference input:/).first().waitFor();
    await stage('Real-time', false);
    await stage('Refined', false);
    await stage('Final', false);
    assert.ok(await page.getByRole('button', { name: 'Record now', exact: true }).isDisabled());
    await stage('Final', true, ['WhisperX']);
    const finalWhisper = page.getByRole('checkbox', { name: 'Final track: WhisperX', exact: true });
    await finalWhisper.uncheck();
    assert.equal(await page.getByRole('checkbox', { name: 'Enable Final', exact: true }).isChecked(), false);
    await page.getByRole('checkbox', { name: 'Enable Final', exact: true }).check();
    assert.ok(await finalWhisper.isChecked());
    await stage('Final', true, ['WhisperX', 'Test-only text', 'Unavailable test']);
    await stage('Refined', true, ['WhisperX', 'Test-only windows']);
    await page.getByRole('spinbutton', { name: 'Refinement window (sec)', exact: true }).fill('10');
    await page.getByRole('tab', { name: 'Recording', exact: true }).click();
    assert.ok(await page.getByLabel('Recording retention', { exact: true }).isDisabled());
    assert.equal(await page.getByLabel('Recording retention', { exact: true }).inputValue(), 'store');
    await page.screenshot({ path: path.join(evidenceDir, 'settings.png'), fullPage: true });
    const multi = await start('multiple');
    await page.getByRole('button', { name: 'Refined real-time', exact: true }).click();
    await waitFor(async () => {
      const panels = page.locator('.realtime-track-panel');
      return await panels.count() === 2 && await panels.nth(0).locator('.bubble').count() > 0 && await panels.nth(1).locator('.bubble').count() > 0;
    }, 'both live refinement tracks before stop');
    const panelBoxes = await page.locator('.realtime-track-panel').evaluateAll(panels => panels.map(p => p.getBoundingClientRect().x));
    assert.notEqual(panelBoxes[0], panelBoxes[1], 'Desktop live tracks should appear side by side');
    await page.screenshot({ path: path.join(evidenceDir, 'live-refined.png'), fullPage: true });
    await stop();
    const saved = await waitFor(async () => {
      const d = await detail(multi);
      return d.transcripts.final.length === 2 && d.transcripts.refined.length >= 2 && d;
    }, 'real WhisperX and synthetic final results');
    assert.deepEqual(saved.session.stream_controls.final_tracks, ['whisperx', 'ui-shadow', 'ui-unavailable']);
    assert.equal(saved.session.stream_controls.track_labels.final['ui-shadow'], 'Test-only text');
    assert.ok(saved.session.has_recording);
    assert.ok(saved.transcripts.final.find(t => t.track_id === 'whisperx').segments.some(s => s.words?.length));
    await page.getByRole('button', { name: 'New session', exact: true }).click();
    await settings();
    await page.getByRole('tab', { name: /^Final/ }).click();
    assert.ok(await page.getByRole('checkbox', { name: 'Final track: Test-only text', exact: true }).isChecked());
    assert.ok(await page.getByRole('checkbox', { name: 'Final track: Unavailable test', exact: true }).isChecked());
    console.log('PASS independent tracks, frozen settings, live results before stop and new-session preferences');

    await page.goto(`${base}/recordings/${multi}?smoke=reload`);
    await page.getByRole('tab', { name: 'Final Transcript (WhisperX)', exact: true }).click();
    await page.locator('.word').first().waitFor();
    await page.locator('.word').nth(1).click();
    await waitFor(() => page.locator('audio').evaluate(a => a.currentTime > 0), 'word seek playback', 15000);
    await page.locator('audio').evaluate(a => a.pause());
    const audioSrc = await page.locator('audio').getAttribute('src');
    await page.getByRole('tab', { name: 'Final Transcript (Test-only text)', exact: true }).click();
    await page.getByText('Synthetic test-only transcript', { exact: true }).waitFor();
    assert.equal(await page.getByRole('tabpanel').locator('.ts, .who, .word').count(), 0);
    assert.equal(await page.locator('audio').getAttribute('src'), audioSrc);
    await page.getByRole('tab', { name: 'Final Transcript (Unavailable test)', exact: true }).click();
    await page.getByText('No result available yet. This does not establish whether the track is processing or failed.', { exact: true }).waitFor();
    await page.getByRole('tab', { name: 'Refined Transcript (Test-only windows)', exact: true }).click();
    await page.reload();
    await page.getByRole('tab', { name: 'Final Transcript (Test-only text)', exact: true }).click();
    await page.getByText('Synthetic test-only transcript', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(evidenceDir, 'saved-text-only.png'), fullPage: true });
    await page.setViewportSize({ width: 600, height: 900 });
    await page.screenshot({ path: path.join(evidenceDir, 'saved-narrow.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    const range = await context.request.get(`${base}/api/recordings/${multi}/audio`, { headers: { Range: 'bytes=0-43' } });
    assert.equal(range.status(), 206);
    assert.equal((await range.body()).subarray(0, 4).toString(), 'RIFF');
    console.log('PASS flat saved tabs, missing results, direct links, reload, text-only and aligned playback');
    if (process.argv.includes('--multiple-only')) return;

    for (const [label, rt, refined, final] of [
      ['alternative-only', false, true, true], ['refined-only', false, true, false],
      ['final-only', false, false, true], ['realtime-only', true, false, false],
    ]) {
      await fresh();
      await stage('Real-time', rt, rt ? ['nemotron'] : undefined);
      await stage('Refined', refined, refined ? ['Test-only windows'] : undefined);
      await stage('Final', final, final ? ['Test-only text'] : undefined);
      const id = await start(label);
      await page.waitForTimeout(4000);
      await stop();
      const result = await waitFor(async () => {
        const d = await detail(id);
        return (!final || d.transcripts.final.length) && (!refined || d.transcripts.refined.length) && d;
      }, label);
      assert.equal(result.session.stream_controls.realtime, rt);
      assert.equal(result.session.stream_controls.refined, refined);
      assert.equal(result.session.stream_controls.final, final);
      for (const [stageName, enabled] of [['final', final], ['refined', refined]]) {
        assert.ok(result.transcripts[stageName].every(row => enabled && row.track_id === 'ui-shadow'));
        if (!enabled) assert.equal(result.transcripts[stageName].length, 0);
      }
      console.log(`PASS ${label}`);
    }
    await fresh();
    const defaults = await start('defaults');
    await page.waitForTimeout(4000);
    await stop();
    const defaultResult = await waitFor(async () => {
      const d = await detail(defaults);
      return d.transcripts.final.length && d.transcripts.refined.length && d;
    }, 'default tracks');
    assert.deepEqual(defaultResult.session.stream_controls.final_tracks, ['whisperx']);
    assert.deepEqual(defaultResult.session.stream_controls.refinement_tracks, ['whisperx']);
    assert.deepEqual(errors, []);
    console.log('PASS default tracks and no browser exceptions');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
