"""Check only the Chromium smoke's sessions for unselected SQL/S3 outcomes.

Uses the local fixture database and object store; never prints transcript data.
Install requirements-final-tracks.txt first. No writes to the stack are made.
"""
import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import uuid

import boto3
import psycopg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=Path("test-results/track-ui/report.json"))
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    assert "failure" not in report and len(report["sessions"]) == 5, "Complete Chromium smoke first"
    database = os.environ.get("TRACK_UI_DATABASE", "postgresql://nanosamurai:nanosamurai@127.0.0.1:5432/nanosamurai")
    endpoint = os.environ.get("TRACK_UI_S3_ENDPOINT", "http://127.0.0.1:4566")
    assert all(urlparse(url).hostname in ("127.0.0.1", "localhost") for url in (database, endpoint))
    s3 = boto3.client("s3", endpoint_url=endpoint, region_name="us-east-1",
                      aws_access_key_id="test", aws_secret_access_key="test")
    bucket = os.environ.get("NANOSAMURAI_RECORDINGS_BUCKET", "nanosamurai-recordings")
    with psycopg.connect(database, connect_timeout=5) as conn:
        for session in report["sessions"]:
            sid = uuid.UUID(session["id"])
            tenant, controls = conn.execute("SELECT tenant_id, stream_controls FROM sessions WHERE id=%s", (sid,)).fetchone()
            rows = conn.execute("SELECT stage,track_id,profile_id,is_primary,status FROM transcript_track_results WHERE session_id=%s", (sid,)).fetchall()
            recording_count = conn.execute("SELECT count(*) FROM recordings WHERE session_id=%s", (sid,)).fetchone()[0]
            assert recording_count == int(session["final"]), "Unexpected full recording retention"
            expected_ids = set(session["track_ids"])
            counts = {}
            for stage, key, prefix in (("refined", "refinement_tracks", "refined-tracks"),
                                       ("final", "final_tracks", "final-tracks")):
                expected = expected_ids if session[stage] else set()
                selections = controls["asr_plan"].get(key, [])
                assert {item["track_id"] for item in selections} == expected
                outcomes = [row for row in rows if row[0] == stage]
                assert {row[1] for row in outcomes} == expected, "SQL contains missing/unselected track outcomes"
                for _, track, profile, primary, status in outcomes:
                    choice = next(item for item in selections if item["track_id"] == track)
                    assert (profile, primary) == (choice["profile_id"], choice["primary"])
                    assert status == ("failed" if track == "failure" else "succeeded")
                objects = []
                for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=f"{prefix}/{tenant}/{sid}/"):
                    objects.extend(item["Key"] for item in page.get("Contents", []))
                assert {key.split("/")[4] for key in objects} == expected, "S3 contains missing/unselected track artifacts"
                counts[stage] = len(outcomes)
            print(f"PASS {session['label']}: selected-only SQL/S3, outcomes={counts}, recordings={recording_count}")


if __name__ == "__main__":
    main()
