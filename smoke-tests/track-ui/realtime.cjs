/** Check speaker placeholders against real Nemotron in local Compose. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.BFF_URL || 'http://127.0.0.1:8000';
assert.ok(['localhost', '127.0.0.1'].includes(new URL(base).hostname), 'Use loopback only');
const evidenceDir = path.resolve(process.env.TRACK_UI_EVIDENCE || '.tmp/track-ui-realtime');
fs.mkdirSync(evidenceDir, { recursive: true });

async function main() {
  const browser = await chromium.launch({ headless: true, args: [
    '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
    `--use-file-for-fake-audio-capture=${path.resolve('tests/data/test_cs.wav')}`,
  ] });
  const page = await browser.newPage({ permissions: ['microphone'], viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(`${base}/live`);
    await page.getByRole('button', { name: 'Session settings', exact: true }).click();
    await page.getByRole('checkbox', { name: 'Enable Real-time', exact: true }).check();
    await page.getByRole('tab', { name: /^Real-time/ }).click();
    const tracks = page.getByTestId('realtime-track-picker').getByRole('checkbox');
    await page.getByRole('checkbox', { name: 'Realtime track: nemotron', exact: true }).check();
    for (let i = 0; i < await tracks.count(); i++) {
      const track = tracks.nth(i);
      if (await track.getAttribute('aria-label') !== 'Realtime track: nemotron') await track.uncheck();
    }
    await page.getByRole('checkbox', { name: 'Enable Refined', exact: true }).uncheck();
    await page.getByRole('checkbox', { name: 'Enable Final', exact: true }).uncheck();
    await page.getByRole('region', { name: 'Session settings', exact: true }).getByRole('button', { name: 'Close', exact: true }).click();
    await page.getByRole('button', { name: 'Record now', exact: true }).click();
    await page.locator('.bubble.draft').first().waitFor({ timeout: 60000 });
    const placeholder = await page.locator('.bubble.draft').first().evaluate(bubble => {
      const message = bubble.closest('.msg');
      return { avatar: message.querySelector('.avatar')?.textContent, who: message.querySelector('.who')?.textContent };
    });
    assert.deepEqual(placeholder, { avatar: '?', who: 'Unknown' });
    await page.waitForFunction(() => {
      const draft = document.querySelector('.bubble.draft')?.closest('.msg');
      const final = [...document.querySelectorAll('.msg')].find(m => {
        const speaker = m.querySelector('.who')?.textContent;
        return m.querySelector('.bubble:not(.draft)') && speaker && speaker !== 'Unknown';
      });
      if (!draft || !final) return false;
      return Math.abs(draft.querySelector('.msgBody').getBoundingClientRect().x -
        final.querySelector('.msgBody').getBoundingClientRect().x) < 1;
    }, null, { timeout: 90000 });
    await page.screenshot({ path: path.join(evidenceDir, 'realtime-speaker-alignment.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('PASS real Nemotron partial retains Unknown/? and aligns with a diarized final turn');
  } finally {
    try {
      const stop = page.getByRole('button', { name: /Stop/ });
      if (await stop.isVisible()) {
        await stop.click();
        await page.getByRole('button', { name: 'New session', exact: true }).waitFor();
      }
    } finally { await browser.close(); }
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
