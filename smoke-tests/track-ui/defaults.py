"""Verify default selections through a real browser and the local Compose models."""
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
evidence = Path('.tmp/default-tracks')
evidence.mkdir(parents=True, exist_ok=True)
fixture = Path(os.environ.get('XAMURAI_SOURCE', '../xamurai')) / 'tests/data/test_en.wav'
stages = [('Real-time', 'realtime', 'realtime_tracks'),
          ('Refined', 'refined', 'refinement_tracks'), ('Final', 'final', 'final_tracks')]
defaults = {'realtime': 'nemotron', 'refined': 'qwen', 'final': 'qwen'}
sessions = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, args=[
        '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
        f'--use-file-for-fake-audio-capture={fixture.resolve()}',
    ])
    page = browser.new_page(permissions=['microphone'], viewport={'width': 1440, 'height': 1000})
    errors, events = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('websocket', lambda socket: socket.on('framereceived', lambda frame: events.append(json.loads(frame)))
            if '/ws/events' in socket.url else None)
    try:
        metadata = page.request.get(f'{base}/api/me').json()
        assert metadata['default_tracks'] == defaults
        assert metadata['realtime_tracks'][0] != defaults['realtime']
        for stage in ['refined', 'final']:
            catalog = [t for t in metadata['async_tracks'] if t['stage'] == stage]
            assert catalog[0]['track_id'] != defaults[stage]
            assert [t['track_id'] for t in catalog if t['default_selected']] == [defaults[stage]]
        for enabled, override in [({'realtime', 'refined', 'final'}, False),
                                  ({'realtime'}, False), ({'refined'}, False),
                                  ({'final'}, False), ({'realtime'}, True)]:
            page.goto(f'{base}/live')
            page.get_by_role('button', name='Session settings', exact=True).click()
            for name, stage, _ in stages:
                page.get_by_role('tab', name=re.compile(f'^{name}')).click()
                prefix = 'Realtime' if stage == 'realtime' else name
                label = defaults[stage] if stage == 'realtime' else 'Qwen3-ASR'
                picker = page.get_by_test_id(f'{prefix.lower()}-track-picker')
                assert picker.locator('input:checked').count() == 1
                assert page.get_by_role('checkbox', name=f'{prefix} track: {label}', exact=True).is_checked()
                page.get_by_role('checkbox', name=f'Enable {name}', exact=True).set_checked(stage in enabled)
            expected_rt = 'faster-whisper' if override else defaults['realtime']
            if override:
                page.get_by_role('tab', name=re.compile('^Real-time')).click()
                page.get_by_role('checkbox', name='Realtime track: faster-whisper', exact=True).check()
                page.get_by_role('checkbox', name='Realtime track: nemotron', exact=True).uncheck()
            page.get_by_role('region', name='Session settings', exact=True).get_by_role('button', name='Close', exact=True).click()
            events.clear()
            with page.expect_websocket(lambda socket: '/ws/audio' in socket.url) as socket_ready:
                page.get_by_role('button', name='Record now', exact=True).click()
            query = parse_qs(urlparse(socket_ready.value.url).query)
            sid = query['session_id'][0]
            assert all(key not in query for _, _, key in stages if key != 'realtime_tracks' or not override)
            if override:
                assert query['realtime_tracks'] == [expected_rt]
            with connect(f'{base.replace("http", "ws", 1)}/ws/events?session_id={sid}') as drain:
                page.wait_for_timeout(13000)
                if 'realtime' in enabled:
                    assert page.locator('.realtime-track-label').all_text_contents() == [expected_rt]
                page.get_by_role('button', name=re.compile('Stop')).click()
                page.get_by_role('button', name='New session', exact=True).wait_for(timeout=60000)
                if 'realtime' in enabled:
                    deadline = time.monotonic() + 180
                    while True:
                        event = json.loads(drain.recv(timeout=max(0, deadline - time.monotonic())))
                        assert event.get('type') != 'error', 'Realtime failed'
                        events.append(event)
                        if event.get('type') == 'status' and event.get('status') == 'stopped':
                            assert event['track'] == expected_rt
                            break
            deadline = time.monotonic() + 900
            while True:
                saved = page.request.get(f'{base}/api/recordings/{sid}').json()
                if all(saved['transcripts'][s] for s in enabled & {'refined', 'final'}):
                    break
                assert time.monotonic() < deadline, 'Batch results timed out'
                page.wait_for_timeout(1000)
            controls = saved['session']['stream_controls']
            for _, stage, key in stages:
                assert controls[stage] == (stage in enabled)
                assert controls[key] == [expected_rt if stage == 'realtime' else defaults[stage]]
            for stage in ['refined', 'final']:
                rows = saved['transcripts'][stage]
                assert bool(rows) == (stage in enabled)
                assert all(r['track_id'] == defaults[stage] and r['full_text'].strip() for r in rows)
            asr = [e for e in events if e.get('type') == 'asr']
            assert bool(asr) == ('realtime' in enabled)
            assert all(e['track'] == expected_rt for e in asr)
            if 'realtime' in enabled:
                assert any(e.get('final') and e.get('text', '').strip() for e in asr)
            sessions.append({'id': sid, 'enabled': sorted(enabled), 'override': override, 'controls': controls})
            (evidence / 'sessions.json').write_text(json.dumps(sessions, indent=2), encoding='utf-8')
            print(f'PASS stages={sorted(enabled)}, override={override}: UI, admission, real results and saved choices', flush=True)
        assert not errors, errors
        print('DEFAULT TRACKS COMPOSE SMOKE PASSED', flush=True)
    finally:
        try:
            stop = page.get_by_role('button', name=re.compile('Stop'))
            if stop.is_visible():
                stop.click()
        finally:
            browser.close()
