"""Browser qualification against the original local Compose stack; no browser mocks."""
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error, sync_playwright

base = os.environ.get('BFF_URL', 'http://127.0.0.1:8000')
assert urlparse(base).hostname in ('localhost', '127.0.0.1'), 'Use loopback only'
evidence = Path(os.environ.get('TRACK_UI_EVIDENCE', '.tmp/track-ui'))
evidence.mkdir(parents=True, exist_ok=True)
sessions = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=[
        '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
        f'--use-file-for-fake-audio-capture={Path("tests/data/test_cs.wav").resolve()}',
    ])
    try:
        context = browser.new_context(permissions=['microphone'], viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def wait_for(fn, label, timeout=240):
            """Poll a boundary while letting Playwright dispatch browser events."""
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                value = fn()
                if value:
                    return value
                page.wait_for_timeout(1000)
            raise AssertionError(f'Timed out: {label}')

        def detail(sid):
            """Read a browser-created session through the public HTTP boundary."""
            return context.request.get(f'{base}/api/recordings/{sid}').json()

        def ready():
            """Allow startup connection failures while waiting for BFF readiness."""
            try:
                return context.request.get(f'{base}/ready').ok
            except Error:
                return False

        wait_for(ready, 'BFF ready', 60)
        page.goto(f'{base}/live')
        metadata = context.request.get(f'{base}/api/me').json()
        assert len(metadata['async_tracks']) >= 2

        if '--verify-labels' in sys.argv:
            first = json.loads((evidence / 'sessions.json').read_text(encoding='utf-8'))[0]
            assert next(t for t in metadata['async_tracks'] if t['stage'] == 'final' and t['track_id'] == 'ui-shadow')['display_name'] == 'Renamed test'
            page.goto(f'{base}/recordings/{first["id"]}?reload=1')
            page.get_by_role('tab', name='Final Transcript (Test-only text)', exact=True).wait_for()
            assert detail(first['id'])['session']['stream_controls']['track_labels']['final']['ui-shadow'] == 'Test-only text'
            print('PASS historical labels survive deployment rename and direct-link reload', flush=True)
            sys.exit(0)

        def settings():
            """Open the settings panel if needed by the next scenario step."""
            if not page.get_by_role('region', name='Session settings', exact=True).is_visible():
                page.get_by_role('button', name='Session settings', exact=True).click()

        def stage(name, enabled, labels=None):
            """Select a stage and its tracks through the visible controls."""
            settings()
            page.get_by_role('checkbox', name=f'Enable {name}', exact=True).set_checked(enabled)
            page.get_by_role('tab', name=re.compile(f'^{name}')).click()
            if labels is not None:
                prefix = 'Realtime' if name == 'Real-time' else name
                for checkbox in page.get_by_test_id(f'{prefix.lower()}-track-picker').get_by_role('checkbox').all():
                    label = checkbox.get_attribute('aria-label').split(': ')[1]
                    checkbox.set_checked(label in labels)

        def start(label):
            """Start capture, save its session ID, and check admission locking."""
            page.get_by_role('region', name='Session settings', exact=True).get_by_role('button', name='Close', exact=True).click()
            with page.expect_response(lambda r: r.url.endswith('/api/sessions') and r.request.method == 'POST') as response:
                page.get_by_role('button', name='Record now', exact=True).click()
            sid = response.value.json()['session_id']
            assert sid
            sessions.append({'label': label, 'id': sid})
            (evidence / 'sessions.json').write_text(json.dumps(sessions, indent=2), encoding='utf-8')
            page.get_by_role('button', name=re.compile('Stop')).wait_for()
            wait_for(lambda: detail(sid)['session']['stream_controls'], 'audio admission', 45)
            settings()
            assert page.get_by_role('checkbox', name='Enable Final', exact=True).is_disabled()
            return sid

        def stop():
            """Finish capture and wait for the New session action."""
            page.get_by_role('button', name=re.compile('Stop')).click()
            page.get_by_role('button', name='New session', exact=True).wait_for()

        def fresh():
            """Reload the Record page to start a scenario with deployment defaults."""
            page.goto(f'{base}/live')
            page.get_by_role('button', name='Session settings', exact=True).wait_for()
            settings()

        settings()
        page.get_by_role('tab', name=re.compile('^Real-time')).click()
        whisper = next(c for c in metadata['realtime_track_capabilities'] if c.get('session_settings', {}).get('window_sec'))
        assert float(page.get_by_role('spinbutton', name=f'{whisper["id"]}: Window (sec)', exact=True).input_value()) == whisper['session_settings']['window_sec']['default']
        if any(c.get('windowed_realtime') and c.get('maximum_audio_seconds', 0) > 0 for c in metadata['realtime_track_capabilities']):
            page.get_by_text(re.compile('Maximum inference input:')).first.wait_for()
        for name in ['Real-time', 'Refined', 'Final']:
            stage(name, False)
        assert page.get_by_role('button', name='Record now', exact=True).is_disabled()
        stage('Final', True, ['WhisperX'])
        final_whisper = page.get_by_role('checkbox', name='Final track: WhisperX', exact=True)
        final_whisper.uncheck()
        assert not page.get_by_role('checkbox', name='Enable Final', exact=True).is_checked()
        page.get_by_role('checkbox', name='Enable Final', exact=True).check()
        assert final_whisper.is_checked()
        stage('Final', True, ['WhisperX', 'Test-only text', 'Unavailable test'])
        stage('Refined', True, ['WhisperX', 'Test-only windows'])
        page.get_by_role('spinbutton', name='Refinement window (sec)', exact=True).fill('10')
        page.get_by_role('tab', name='Recording', exact=True).click()
        assert page.get_by_label('Recording retention', exact=True).is_disabled()
        assert page.get_by_label('Recording retention', exact=True).input_value() == 'store'
        page.screenshot(path=evidence / 'settings.png', full_page=True)
        multi = start('multiple')
        page.get_by_role('button', name='Refined real-time', exact=True).click()
        panels = page.locator('.realtime-track-panel')
        wait_for(lambda: panels.count() == 2 and all(p.locator('.bubble').count() for p in panels.all()),
                 'both live refinement tracks before stop')
        assert panels.nth(0).bounding_box()['x'] != panels.nth(1).bounding_box()['x'], 'Desktop live tracks should appear side by side'
        page.screenshot(path=evidence / 'live-refined.png', full_page=True)
        stop()
        saved = wait_for(lambda: d if len((d := detail(multi))['transcripts']['final']) == 2 and len(d['transcripts']['refined']) >= 2 else None,
                         'real WhisperX and synthetic final results')
        assert saved['session']['stream_controls']['final_tracks'] == ['whisperx', 'ui-shadow', 'ui-unavailable']
        assert saved['session']['stream_controls']['track_labels']['final']['ui-shadow'] == 'Test-only text'
        assert saved['session']['has_recording']
        assert any(s.get('words') for t in saved['transcripts']['final'] if t['track_id'] == 'whisperx' for s in t['segments'])
        page.get_by_role('button', name='New session', exact=True).click()
        settings()
        page.get_by_role('tab', name=re.compile('^Final')).click()
        assert page.get_by_role('checkbox', name='Final track: Test-only text', exact=True).is_checked()
        assert page.get_by_role('checkbox', name='Final track: Unavailable test', exact=True).is_checked()
        print('PASS independent tracks, frozen settings, live results before stop and new-session preferences', flush=True)

        page.goto(f'{base}/recordings/{multi}?smoke=reload')
        page.get_by_role('tab', name='Final Transcript (WhisperX)', exact=True).click()
        page.locator('.word').first.wait_for()
        page.locator('.word').nth(1).click()
        wait_for(lambda: page.locator('audio').evaluate('a => a.currentTime > 0'), 'word seek playback', 15)
        page.locator('audio').evaluate('a => a.pause()')
        audio_src = page.locator('audio').get_attribute('src')
        page.get_by_role('tab', name='Final Transcript (Test-only text)', exact=True).click()
        page.get_by_text('Synthetic test-only transcript', exact=True).wait_for()
        assert page.get_by_role('tabpanel').locator('.ts, .who, .word').count() == 0
        assert page.locator('audio').get_attribute('src') == audio_src
        page.get_by_role('tab', name='Final Transcript (Unavailable test)', exact=True).click()
        page.get_by_text('No result available yet. This does not establish whether the track is processing or failed.', exact=True).wait_for()
        page.get_by_role('tab', name='Refined Transcript (Test-only windows)', exact=True).click()
        page.reload()
        page.get_by_role('tab', name='Final Transcript (Test-only text)', exact=True).click()
        page.get_by_text('Synthetic test-only transcript', exact=True).wait_for()
        page.screenshot(path=evidence / 'saved-text-only.png', full_page=True)
        page.set_viewport_size({'width': 600, 'height': 900})
        page.screenshot(path=evidence / 'saved-narrow.png', full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1000})
        audio_range = context.request.get(f'{base}/api/recordings/{multi}/audio', headers={'Range': 'bytes=0-43'})
        assert audio_range.status == 206
        assert audio_range.body()[:4] == b'RIFF'
        print('PASS flat saved tabs, missing results, direct links, reload, text-only and aligned playback', flush=True)
        if '--multiple-only' in sys.argv:
            assert not errors, errors
            sys.exit(0)

        for label, rt, refined, final in [
            ('alternative-only', False, True, True), ('refined-only', False, True, False),
            ('final-only', False, False, True), ('realtime-only', True, False, False),
        ]:
            fresh()
            stage('Real-time', rt, ['nemotron'] if rt else None)
            stage('Refined', refined, ['Test-only windows'] if refined else None)
            stage('Final', final, ['Test-only text'] if final else None)
            sid = start(label)
            page.wait_for_timeout(4000)
            stop()
            result = wait_for(lambda: d if (d := detail(sid)) and (not final or d['transcripts']['final']) and (not refined or d['transcripts']['refined']) else None, label)
            assert result['session']['stream_controls']['realtime'] == rt
            assert result['session']['stream_controls']['refined'] == refined
            assert result['session']['stream_controls']['final'] == final
            for stage_name, enabled in [('final', final), ('refined', refined)]:
                assert all(enabled and row['track_id'] == 'ui-shadow' for row in result['transcripts'][stage_name])
                if not enabled:
                    assert not result['transcripts'][stage_name]
            print(f'PASS {label}', flush=True)
        fresh()
        defaults = start('defaults')
        page.wait_for_timeout(4000)
        stop()
        default_result = wait_for(lambda: d if (d := detail(defaults))['transcripts']['final'] and d['transcripts']['refined'] else None, 'default tracks')
        assert default_result['session']['stream_controls']['final_tracks'] == ['whisperx']
        assert default_result['session']['stream_controls']['refinement_tracks'] == ['whisperx']
        assert not errors, errors
        print('PASS default tracks and no browser exceptions', flush=True)
    finally:
        browser.close()
