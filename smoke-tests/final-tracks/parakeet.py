"""Real Parakeet/WhisperX Compose smoke, reusing the existing final-track probe."""
import io
import os
import uuid
import wave

import smoke as s
from websockets.exceptions import InvalidStatus


def main():
    s.CONSUMER.subscribe(list(s.TOPICS))
    s.wait_for(lambda: {p.topic for p in s.CONSUMER.assignment()} == set(s.TOPICS),
               "Kafka observation ready", 30)
    s.wait_for(lambda: s.http("/health")[0] == 200, "BFF ready", 60)
    with wave.open("/probe/test_cs.wav", "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        speech = wav.readframes(30 * 16000)

    session = s.new_session()
    try:
        s.stream(session, speech, "whisperx,parakeet", retained=False)
        raise AssertionError("Non-retained multi-track audio was accepted")
    except InvalidStatus as error:
        assert error.response.status_code == 400
    s.stream(session, speech, "parakeet,whisperx", refined=True)
    s.wait_for(lambda: len(s.rows(session)) == 2, "both real final tracks persisted", 900)
    saved = s.rows(session)
    assert {r["track_id"] for r in saved} == {"whisperx", "parakeet"}
    assert len({r["recording_id"] for r in saved}) == 1
    assert all(r["full_text"].strip() for r in saved)
    s.wait_for(lambda: s.DB.execute("SELECT count(*) AS n FROM session_transcripts "
               "WHERE session_id=%s AND type='refined' AND track_id='whisperx'",
               (session,)).fetchone()["n"] == 2, "both WhisperX refinement windows persisted", 900)
    refined = s.DB.execute("SELECT full_text,segments FROM session_transcripts "
                          "WHERE session_id=%s AND type='refined'", (session,)).fetchall()
    assert all(row["full_text"].strip() and row["segments"] for row in refined)
    parakeet = next(r for r in saved if r["track_id"] == "parakeet")
    assert parakeet["model"] == "nvidia/parakeet-tdt-0.6b-v3"
    words = [w for segment in parakeet["segments"] for w in segment.get("words", [])]
    assert words and any(segment.get("speaker", "").startswith("SPEAKER_")
                         for segment in parakeet["segments"])
    assert all(0 <= w["start_s"] <= w["end_s"] <= len(speech) / 32000 for w in words)
    assert "".join(parakeet["full_text"].split()) == "".join(w["text"].replace(" ", "") for w in words)
    status, detail, _ = s.http(f"/api/recordings/{session}?track_id=parakeet")
    assert status == 200 and len(detail["transcripts"]["final"]) == 1
    result = detail["transcripts"]["final"][0]
    assert (result["full_text"], result["segments"]) == (parakeet["full_text"], parakeet["segments"])
    status, audio, _ = s.http(f"/api/recordings/{session}/audio")
    assert status == 200
    with wave.open(io.BytesIO(audio), "rb") as wav:
        assert wav.readframes(wav.getnframes()) == speech
    assert s.http(f"/api/recordings/{session}/audio", headers={"Range": "bytes=0-43"})[0] == 206
    print("PASS Parakeet text, diarization, word timing, filtering and shared playback")

    s.wait_for(lambda: s.EVENTS.get((session, "recordings.finished")), "recording event observed")
    _, finished = s.EVENTS[(session, "recordings.finished")][-1]
    assert dict(finished.headers())["x-final-tracks"] == b"parakeet,whisperx"
    s.wait_for(lambda: len(s.EVENTS.get((session, "transcripts.final"), [])) == 2,
               "both final events observed")
    s.replay(finished)
    s.wait_for(lambda: len(s.EVENTS[(session, "transcripts.final")]) >= 4, "real inference replayed", 900)
    last = s.EVENTS[(session, "transcripts.final")][-1][1]
    s.wait_for(lambda: s.committed(s.PERSISTOR_GROUP, last), "Persistor consumed replay")
    assert s.rows(session) == saved
    print("PASS replay preserves the first result for both tracks")

    for pcm, tracks in [(bytes(32000), "parakeet,whisperx"), (speech, "parakeet"), (speech, "whisperx")]:
        selected = s.new_session()
        s.stream(selected, pcm, tracks)
        s.wait_for(lambda: len(s.rows(selected)) == len(tracks.split(",")),
                   f"selection {tracks} completed", 900)
        rows = s.rows(selected)
        assert {r["track_id"] for r in rows} == set(tracks.split(","))
        if not any(pcm):
            assert all(not r["full_text"].strip() and not r["segments"] for r in rows)
        s.wait_for(lambda: s.EVENTS.get((selected, "recordings.finished")), "selection event observed")
        event = s.EVENTS[(selected, "recordings.finished")][-1][1]
        for group in ["finalizer.parakeet", os.getenv("WHISPERX_FINALIZER_GROUP", "finalizer-worker")]:
            s.wait_for(lambda: s.committed(group, event), "selected or skipped input committed", 900)

    foreign, foreign_session = uuid.uuid4(), uuid.uuid4()
    s.DB.execute("INSERT INTO tenants(id,name) VALUES (%s,'Parakeet smoke tenant')", (foreign,))
    s.DB.execute("INSERT INTO sessions(id,tenant_id,session_key) VALUES (%s,%s,%s)",
                 (foreign_session, foreign, str(foreign_session)))
    assert s.http(f"/api/recordings/{foreign_session}")[0] == 404
    assert s.http(f"/api/recordings/{foreign_session}/audio")[0] == 404
    try:
        s.stream(str(foreign_session), speech, "parakeet")
        raise AssertionError("Foreign tenant accepted audio")
    except InvalidStatus as error:
        assert error.response.status_code == 403
    print("PASS tenant denial; PARAKEET COMPOSE SMOKE PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        s.CONSUMER.close()
        s.DB.close()
