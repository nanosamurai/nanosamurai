"""Real Qwen workers through Compose BFF, Kafka, recording storage and Postgres."""
import io
import json
import time
import uuid
import wave
from urllib.parse import urlencode

from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect
import smoke as s

s.TOPICS["transcripts.refined"] = s.pb.RefinedEvent
MODEL = "Qwen/Qwen3-ASR-0.6B"


def refined_rows(session):
    return s.DB.execute("SELECT track_id,model,full_text,segments,segment_start_s,segment_end_s "
                        "FROM session_transcripts WHERE session_id=%s AND type='refined' "
                        "ORDER BY segment_start_s", (session,)).fetchall()


def audio_socket(session, *, final=True, refined=True, track="qwen"):
    params = dict(session_id=session, sample_rate=16000, lang="en", realtime="false",
                  final=str(final).lower(), refined=str(refined).lower(),
                  store_recording="true", refinement_window_sec=10)
    if track is not None:
        params.update(final_tracks=track, refinement_tracks=track)
    return connect(s.BFF.replace("http", "ws", 1) + "/ws/audio?" + urlencode(params), open_timeout=15)


def send(ws, pcm):
    for offset in range(0, len(pcm), 6400):
        ws.send(pcm[offset:offset + 6400])
        time.sleep(.02)


def main():
    s.CONSUMER.subscribe(list(s.TOPICS))
    s.wait_for(lambda: {p.topic for p in s.CONSUMER.assignment()} == set(s.TOPICS), "Kafka observer ready", 40)
    s.wait_for(lambda: s.http("/ready")[0] == 200, "BFF ready", 60)
    with wave.open("/probe/test_en.wav", "rb") as wav:
        fixture = wav.readframes(wav.getnframes())
    speech = (fixture * 3)[:round(23.125 * 32000)]
    session = s.new_session()
    live = []
    with connect(s.BFF.replace("http", "ws", 1) + "/ws/events?" + urlencode({"session_id": session})) as events:
        with audio_socket(session) as ws:
            send(ws, speech)
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                s.pump()
                try:
                    event = json.loads(events.recv(timeout=.1))
                    if event.get("type") == "refined":
                        live.append(event)
                except TimeoutError:
                    pass
                if len(refined_rows(session)) == 3 and {e["slice_index"] for e in live} == {0, 1, 2}:
                    break
            else:
                raise AssertionError("Qwen windows and idle tail did not arrive live")
    assert all(e["track_id"] == "qwen" and e.get("speaker") for e in live)
    assert all(e["window_start_s"] <= e["start_s"] < e["end_s"] <= e["window_end_s"] for e in live)
    refined = refined_rows(session)
    assert [(r["segment_start_s"], r["segment_end_s"]) for r in refined] == [(0, 10), (10, 20), (20, 23.125)]
    s.wait_for(lambda: len(s.rows(session)) == 1, "Qwen final persisted", 900)
    final = s.rows(session)
    assert all(segment.get("words") for segment in final[0]["segments"])
    for row in final + refined:
        assert row["track_id"] == "qwen" and row["model"] == MODEL and row["full_text"].strip()
        start, end = row.get("segment_start_s", 0), row.get("segment_end_s", 23.125)
        assert row["segments"] and all(segment.get("speaker") and
               start <= segment["start_s"] < segment["end_s"] <= end for segment in row["segments"])
        assert row["full_text"] == " ".join(segment["text"] for segment in row["segments"])
        assert any(segment.get("words") for segment in row["segments"])
        for segment in row["segments"]:
            words = segment.get("words", [])
            if words:
                assert "".join(w["text"] for w in words) == segment["text"]
            assert all(segment["start_s"] <= w["start_s"] < w["end_s"] <= segment["end_s"] for w in words)
            assert all(a["start_s"] <= b["start_s"] for a, b in zip(words, words[1:]))
    status, history, _ = s.http(f"/api/recordings/{session}?track_id=qwen")
    assert status == 200
    for stage, rows in [("final", final), ("refined", refined)]:
        assert [(r["full_text"], r["segments"]) for r in history["transcripts"][stage]] == [
            (r["full_text"], r["segments"]) for r in rows]
    status, audio, _ = s.http(f"/api/recordings/{session}/audio")
    assert status == 200
    with wave.open(io.BytesIO(audio), "rb") as wav:
        assert wav.readframes(wav.getnframes()) == speech
    assert s.http(f"/api/recordings/{session}/audio", headers={"Range": "bytes=0-43"})[0] == 206
    print("PASS live Qwen windows/tail, timed speakers/words, final/refined history and exact WAV/range playback")
    print(f"QWEN_COMPOSE_SMOKE_SESSION={session}")

    s.wait_for(lambda: s.EVENTS.get((session, "recordings.finished")), "recording event observed")
    finished = s.EVENTS[(session, "recordings.finished")][-1][1]
    s.replay(finished)
    s.wait_for(lambda: len(s.EVENTS.get((session, "transcripts.final"), [])) >= 2, "real final inference replayed", 900)
    s.wait_for(lambda: s.committed(s.PERSISTOR_GROUP, s.EVENTS[(session, "transcripts.final")][-1][1]),
               "final replay persisted")
    assert s.rows(session) == final
    s.wait_for(lambda: len(s.EVENTS.get((session, "transcripts.refined"), [])) == 3, "refined events observed")
    for event, message in list(s.EVENTS[(session, "transcripts.refined")]):
        assert event.track_id == "qwen" and event.refinement_model == MODEL and message.key() == session.encode()
        event.text = "Replay must not overwrite the first result"
        s.replay(message, event.SerializeToString())
    s.wait_for(lambda: len(s.EVENTS[(session, "transcripts.refined")]) == 6, "refined replay observed")
    s.wait_for(lambda: s.committed("samuraipersistor-refined", s.EVENTS[(session, "transcripts.refined")][-1][1]),
               "refined replay persisted")
    assert refined_rows(session) == refined

    for pcm, final_on, refined_on, track in [
        (speech[:12 * 32000], True, False, "qwen"),
        (speech[:12 * 32000], False, True, "qwen"),
        (bytes(32000), True, True, "qwen"),
        (bytes(32000), True, True, "whisperx"),
        (bytes(32000), True, True, None),
    ]:
        selected = s.new_session()
        with audio_socket(selected, final=final_on, refined=refined_on, track=track) as ws:
            send(ws, pcm)
        s.wait_for(lambda: sum(len(e.pcm16_le) for e, _ in s.EVENTS.get((selected, "audio.raw"), [])) == len(pcm),
                   "selection audio observed")
        s.wait_for(lambda: s.committed("refinement.qwen", s.EVENTS[(selected, "audio.raw")][-1][1]),
                   "refinement completed or skipped", 900)
        if final_on:
            s.wait_for(lambda: s.EVENTS.get((selected, "recordings.finished")), "selection recording observed")
            s.wait_for(lambda: s.committed("finalizer.qwen", s.EVENTS[(selected, "recordings.finished")][-1][1]),
                       "final completed or skipped", 900)
        expected_final = int(final_on and track == "qwen")
        expected_refined = (2 if len(pcm) > 10 * 32000 else 1) if refined_on and track == "qwen" else 0
        s.wait_for(lambda: len([r for r in s.rows(selected) if r["track_id"] == "qwen"]) == expected_final and
                   len([r for r in refined_rows(selected) if r["track_id"] == "qwen"]) == expected_refined,
                   "independent stages and selected Qwen rows")
        if track == "qwen" and not any(pcm):
            assert all(not row["full_text"].strip() for row in s.rows(selected) + refined_rows(selected))

    foreign, foreign_session = uuid.uuid4(), uuid.uuid4()
    s.DB.execute("INSERT INTO tenants(id,name) VALUES (%s,'Qwen smoke tenant')", (foreign,))
    s.DB.execute("INSERT INTO sessions(id,tenant_id,session_key) VALUES (%s,%s,%s)",
                 (foreign_session, foreign, str(foreign_session)))
    assert s.http(f"/api/recordings/{foreign_session}?track_id=qwen")[0] == 404
    assert s.http(f"/api/recordings/{foreign_session}/audio")[0] == 404
    try:
        with audio_socket(str(foreign_session)):
            raise AssertionError("Foreign tenant accepted Qwen audio")
    except InvalidStatus as error:
        assert error.response.status_code == 403
    print("PASS independent stages, committed skips/defaults, silence, replay and tenant denial")
    print("QWEN COMPOSE SMOKE PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        s.CONSUMER.close()
        s.DB.close()
