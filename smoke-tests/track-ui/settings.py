"""Exercise service-owned settings through the real browser and local ASR services."""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright
from websockets.sync.client import connect

base = os.environ.get('BFF_URL', 'http://127.0.0.1:8000')
assert urlparse(base).hostname in ('localhost', '127.0.0.1'), 'Use loopback only'
evidence = Path(os.environ.get('TRACK_UI_EVIDENCE', '.tmp/realtime-settings'))
evidence.mkdir(parents=True, exist_ok=True)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=[
        '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
        f'--use-file-for-fake-audio-capture={Path("tests/data/test_cs.wav").resolve()}',
    ])
    page = browser.new_page(permissions=['microphone'], viewport={'width': 1440, 'height': 1000})
    errors, events, sessions = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('websocket', lambda socket: socket.on('framereceived', lambda frame: events.append(json.loads(frame)))
            if '/ws/events' in socket.url else None)
    try:
        metadata = page.request.get(f'{base}/api/me').json()
        definitions = {c['id']: c['session_settings'] for c in metadata['realtime_track_capabilities']}
        assert set(definitions['nemotron']) == {'endpointing_silence_ms'}
        assert definitions['faster-whisper']['partial_enable']['type'] == 'boolean'
        for silence, partial in [(800, False), (3000, True)]:
            page.goto(f'{base}/live')
            page.get_by_role('button', name='Session settings', exact=True).click()
            page.get_by_role('checkbox', name='Enable Real-time', exact=True).check()
            page.get_by_role('tab', name=re.compile('^Real-time')).click()
            for track in ['faster-whisper', 'nemotron']:
                page.get_by_role('checkbox', name=f'Realtime track: {track}', exact=True).check()
            for name in ['Refined', 'Final']:
                page.get_by_role('checkbox', name=f'Enable {name}', exact=True).uncheck()
            window = page.get_by_role('spinbutton', name='faster-whisper: Window (sec)', exact=True)
            endpoint = page.get_by_role('spinbutton', name='nemotron: Endpointing silence (ms)', exact=True)
            assert int(endpoint.input_value()) == definitions['nemotron']['endpointing_silence_ms']['default']
            assert float(window.input_value()) == definitions['faster-whisper']['window_sec']['default']
            assert window.get_attribute('step') == '0.01'
            assert endpoint.get_attribute('step') == '1'
            endpoint.fill('99999')
            assert endpoint.input_value() == '30000'
            endpoint.fill(str(silence))
            window.fill('4')
            page.get_by_role('spinbutton', name='faster-whisper: Overlap (sec)', exact=True).fill('0.257')
            page.get_by_role('checkbox', name='faster-whisper: Show partial text', exact=True).set_checked(partial)
            expected = {
                'faster-whisper': {'window_sec': 4, 'overlap_sec': 0.26,
                                  'emit_every_sec': definitions['faster-whisper']['emit_every_sec']['default'],
                                  'partial_enable': partial},
                'nemotron': {'endpointing_silence_ms': silence},
            }
            page.screenshot(path=evidence / f'settings-{silence}.png', full_page=True)
            page.get_by_role('region', name='Session settings', exact=True).get_by_role('button', name='Close', exact=True).click()
            start = len(events)
            with page.expect_websocket(lambda socket: '/ws/audio' in socket.url) as socket_ready:
                page.get_by_role('button', name='Record now', exact=True).click()
            query = parse_qs(urlparse(socket_ready.value.url).query)
            sid = query['session_id'][0]
            assert json.loads(query['realtime_settings'][0]) == expected
            page.get_by_role('button', name='Session settings', exact=True).click()
            assert endpoint.is_disabled()
            page.get_by_role('region', name='Session settings', exact=True).get_by_role('button', name='Close', exact=True).click()
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline and not all(
                any(e.get('type') == 'asr' and e.get('track') == track and e.get('final') for e in events[start:])
                for track in ['faster-whisper', 'nemotron']
            ):
                page.wait_for_timeout(500)
            # The UI's event connection has a shorter shutdown timeout than ASR draining.
            with connect(f'{base.replace("http", "ws", 1)}/ws/events?session_id={sid}') as drain:
                page.get_by_role('button', name=re.compile('Stop')).click()
                page.get_by_role('button', name='New session', exact=True).wait_for()
                pending, deadline = {'faster-whisper', 'nemotron'}, time.monotonic() + 180
                while pending:
                    event = json.loads(drain.recv(timeout=max(0, deadline - time.monotonic())))
                    assert event.get('type') != 'error', event
                    if event.get('type') == 'status' and event.get('status') == 'stopped':
                        pending.discard(event.get('track'))
            asr = [e for e in events[start:] if e.get('type') == 'asr' and e.get('session_id') == sid]
            for track in ['faster-whisper', 'nemotron']:
                assert any(e['track'] == track and e['final'] for e in asr), f'{track} final missing'
            assert any(e['track'] == 'faster-whisper' and not e['final'] for e in asr) == partial
            detail = page.request.get(f'{base}/api/recordings/{sid}').json()
            assert detail['session']['stream_controls']['realtime_settings'] == expected
            sessions.append({'id': sid, 'label': f'silence-{silence}', 'realtime_settings': expected})
            (evidence / 'sessions.json').write_text(json.dumps(sessions, indent=2), encoding='utf-8')
            (evidence / f'timings-{silence}.json').write_text(json.dumps([
                {key: e.get(key) for key in ['track', 'final', 'start_s', 'end_s']} for e in asr
            ], indent=2), encoding='utf-8')
            print(f'PASS silence={silence}, partials={partial}: UI limits, admission, locked controls, real ASR and saved settings', flush=True)
        assert not errors, errors
    finally:
        try:
            stop = page.get_by_role('button', name=re.compile('Stop'))
            if stop.is_visible():
                stop.click()
        finally:
            browser.close()
