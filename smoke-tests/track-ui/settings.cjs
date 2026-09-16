/** Exercise service-owned settings through the real browser and local ASR services. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.BFF_URL || 'http://127.0.0.1:8000';
assert.ok(['localhost', '127.0.0.1'].includes(new URL(base).hostname));
const evidence = path.resolve(process.env.TRACK_UI_EVIDENCE || '.tmp/realtime-settings');
fs.mkdirSync(evidence, { recursive: true });

async function main() {
  const browser = await chromium.launch({ headless: true, args: [
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
    `--use-file-for-fake-audio-capture=${path.resolve('tests/data/test_cs.wav')}`,
  ] });
  const page = await browser.newPage({ permissions: ['microphone'], viewport: { width: 1440, height: 1000 } });
  const errors = [], events = [], sessions = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('websocket', socket => {
    if (socket.url().includes('/ws/events')) socket.on('framereceived', frame => events.push(JSON.parse(frame.payload)));
  });
  try {
    const metadata = await (await page.request.get(`${base}/api/me`)).json();
    const definitions = Object.fromEntries(metadata.realtime_track_capabilities.map(c => [c.id, c.session_settings]));
    assert.deepEqual(Object.keys(definitions.nemotron), ['endpointing_silence_ms']);
    assert.equal(definitions['faster-whisper'].partial_enable.type, 'boolean');
    for (const [silence, partial] of [[800, false], [3000, true]]) {
      await page.goto(`${base}/live`);
      await page.getByRole('button', { name: 'Session settings', exact: true }).click();
      await page.getByRole('checkbox', { name: 'Enable Real-time', exact: true }).check();
      await page.getByRole('tab', { name: /^Real-time/ }).click();
      for (const id of ['faster-whisper', 'nemotron'])
        await page.getByRole('checkbox', { name: `Realtime track: ${id}`, exact: true }).check();
      for (const name of ['Refined', 'Final'])
        await page.getByRole('checkbox', { name: `Enable ${name}`, exact: true }).uncheck();
      const window = page.getByRole('spinbutton', { name: 'faster-whisper: Window (sec)', exact: true });
      const endpoint = page.getByRole('spinbutton', { name: 'nemotron: Endpointing silence (ms)', exact: true });
      assert.equal(Number(await endpoint.inputValue()), definitions.nemotron.endpointing_silence_ms.default);
      assert.equal(Number(await window.inputValue()), definitions['faster-whisper'].window_sec.default);
      assert.equal(await window.getAttribute('step'), '0.01');
      assert.equal(await endpoint.getAttribute('step'), '1');
      await endpoint.fill('99999');
      assert.equal(await endpoint.inputValue(), '30000');
      await endpoint.fill(String(silence));
      await window.fill('4');
      await page.getByRole('spinbutton', { name: 'faster-whisper: Overlap (sec)', exact: true }).fill('0.257');
      await page.getByRole('checkbox', { name: 'faster-whisper: Show partial text', exact: true }).setChecked(partial);
      const expected = {
        'faster-whisper': { window_sec: 4, overlap_sec: 0.26, emit_every_sec: definitions['faster-whisper'].emit_every_sec.default, partial_enable: partial },
        nemotron: { endpointing_silence_ms: silence },
      };
      await page.screenshot({ path: path.join(evidence, `settings-${silence}.png`), fullPage: true });
      await page.getByRole('region', { name: 'Session settings', exact: true }).getByRole('button', { name: 'Close', exact: true }).click();
      const socketReady = page.waitForEvent('websocket', socket => socket.url().includes('/ws/audio'));
      await page.getByRole('button', { name: 'Record now', exact: true }).click();
      const socket = await socketReady;
      const query = new URL(socket.url()).searchParams;
      const id = query.get('session_id');
      assert.deepEqual(JSON.parse(query.get('realtime_settings')), expected);
      const start = events.length;
      await page.getByRole('button', { name: 'Session settings', exact: true }).click();
      assert.ok(await endpoint.isDisabled());
      await page.getByRole('region', { name: 'Session settings', exact: true }).getByRole('button', { name: 'Close', exact: true }).click();
      const deadline = Date.now() + 90000;
      while (Date.now() < deadline && !['faster-whisper', 'nemotron'].every(track =>
        events.slice(start).some(e => e.type === 'asr' && e.track === track && e.final)))
        await page.waitForTimeout(500);
      await page.getByRole('button', { name: /Stop/ }).click();
      await page.getByRole('button', { name: 'New session', exact: true }).waitFor();
      await page.waitForTimeout(1500);
      const asr = events.slice(start).filter(e => e.type === 'asr' && e.session_id === id);
      for (const track of ['faster-whisper', 'nemotron']) assert.ok(asr.some(e => e.track === track && e.final), `${track} final missing`);
      assert.equal(asr.some(e => e.track === 'faster-whisper' && !e.final), partial);
      const detail = await (await page.request.get(`${base}/api/recordings/${id}`)).json();
      assert.deepEqual(detail.session.stream_controls.realtime_settings, expected);
      sessions.push({ id, label: `silence-${silence}`, realtime_settings: expected });
      fs.writeFileSync(path.join(evidence, 'sessions.json'), JSON.stringify(sessions, null, 2));
      fs.writeFileSync(path.join(evidence, `timings-${silence}.json`), JSON.stringify(asr.map(({ track, final, start_s, end_s }) => ({ track, final, start_s, end_s })), null, 2));
      console.log(`PASS silence=${silence}, partials=${partial}: UI limits, admission, locked controls, real ASR and saved settings`);
    }
    assert.deepEqual(errors, []);
  } finally {
    const stop = page.getByRole('button', { name: /Stop/ });
    if (await stop.isVisible()) await stop.click();
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
