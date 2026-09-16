"""Check speaker placeholders against real Nemotron in local Compose."""
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

base = os.environ.get('BFF_URL', 'http://127.0.0.1:8000')
assert urlparse(base).hostname in ('localhost', '127.0.0.1'), 'Use loopback only'
evidence = Path(os.environ.get('TRACK_UI_EVIDENCE', '.tmp/track-ui-realtime'))
evidence.mkdir(parents=True, exist_ok=True)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=[
        '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
        f'--use-file-for-fake-audio-capture={Path("tests/data/test_cs.wav").resolve()}',
    ])
    page = browser.new_page(permissions=['microphone'], viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(f'{base}/live')
        page.get_by_role('button', name='Session settings', exact=True).click()
        page.get_by_role('checkbox', name='Enable Real-time', exact=True).check()
        page.get_by_role('tab', name=re.compile('^Real-time')).click()
        tracks = page.get_by_test_id('realtime-track-picker').get_by_role('checkbox')
        page.get_by_role('checkbox', name='Realtime track: nemotron', exact=True).check()
        for track in tracks.all():
            if track.get_attribute('aria-label') != 'Realtime track: nemotron':
                track.uncheck()
        page.get_by_role('checkbox', name='Enable Refined', exact=True).uncheck()
        page.get_by_role('checkbox', name='Enable Final', exact=True).uncheck()
        page.get_by_role('region', name='Session settings', exact=True).get_by_role('button', name='Close', exact=True).click()
        page.get_by_role('button', name='Record now', exact=True).click()
        page.locator('.bubble.draft').first.wait_for(timeout=60000)
        placeholder = page.locator('.bubble.draft').first.evaluate('''bubble => {
          const message = bubble.closest('.msg');
          return {avatar: message.querySelector('.avatar')?.textContent, who: message.querySelector('.who')?.textContent};
        }''')
        assert placeholder == {'avatar': '?', 'who': 'Unknown'}
        page.wait_for_function('''() => {
          const draft = document.querySelector('.bubble.draft')?.closest('.msg');
          const final = [...document.querySelectorAll('.msg')].find(m => {
            const speaker = m.querySelector('.who')?.textContent;
            return m.querySelector('.bubble:not(.draft)') && speaker && speaker !== 'Unknown';
          });
          if (!draft || !final) return false;
          return Math.abs(draft.querySelector('.msgBody').getBoundingClientRect().x -
            final.querySelector('.msgBody').getBoundingClientRect().x) < 1;
        }''', timeout=90000)
        page.screenshot(path=evidence / 'realtime-speaker-alignment.png', full_page=True)
        assert not errors, errors
        print('PASS real Nemotron partial retains Unknown/? and aligns with a diarized final turn', flush=True)
    finally:
        try:
            stop = page.get_by_role('button', name=re.compile('Stop'))
            if stop.is_visible():
                stop.click()
                page.get_by_role('button', name='New session', exact=True).wait_for()
        finally:
            browser.close()
