"""Guard deployment mistakes that would leave visible selections without workers."""
import copy
import json
import unittest

from check_track_catalog import validate


def fixture():
    return {"services": {
        "samuraibff": {"ports": [{"published": "8000", "host_ip": "127.0.0.1"}],
                       "environment": {
                           "SAMURAIBFF_FINAL_TRACKS_ENABLED": "true",
                           "SAMURAIBFF_FINAL_TRACKS_JSON": json.dumps([
                               {"track_id": "whisperx", "profile_id": "whisperx-medium-final-r1",
                                "primary": True, "default_selected": True}])}},
        "finalizer_worker": {"environment": {
            "FINAL_TRACK_ID": "whisperx", "FINAL_PROFILE_ID": "whisperx-medium-final-r1"}}}}


class CatalogTests(unittest.TestCase):
    def test_matching_primary_and_loopback(self):
        validate(fixture())

    def test_rejects_missing_worker_wrong_profile_and_wrong_stage(self):
        for field, value in (("FINAL_TRACK_ID", "other"),
                             ("FINAL_PROFILE_ID", "different-revision"),
                             ("ASR_TRACK_STAGE", "refined")):
            data = fixture()
            data["services"]["finalizer_worker"]["environment"][field] = value
            with self.assertRaises(ValueError):
                validate(data)

    def test_rejects_external_bind(self):
        for host in ("0.0.0.0", "192.168.1.2", None):
            data = fixture()
            data["services"]["samuraibff"]["ports"][0]["host_ip"] = host
            with self.assertRaises(ValueError):
                validate(data)

    def test_synthetic_requires_both_explicit_gates(self):
        data = fixture()
        bff = data["services"]["samuraibff"]["environment"]
        worker = data["services"]["finalizer_worker"]["environment"]
        bff["SAMURAIBFF_FINAL_TRACKS_JSON"] = bff["SAMURAIBFF_FINAL_TRACKS_JSON"].replace("whisperx-medium-final-r1", "test-final-r1")
        worker["FINAL_PROFILE_ID"] = "test-final-r1"
        with self.assertRaises(ValueError):
            validate(data)
        bff["SAMURAIBFF_FINAL_TRACK_TEST_PROFILE_ENABLED"] = "true"
        with self.assertRaises(ValueError):
            validate(data)
        worker["FINAL_TRACK_TEST_PROFILE_ENABLED"] = "true"
        validate(data)

    def test_rejects_invalid_primary_and_duplicates(self):
        for mutation in (lambda entries: entries[0].update(primary=False),
                         lambda entries: entries[0].update(default_selected=False),
                         lambda entries: entries.append(copy.copy(entries[0]))):
            data = fixture()
            bff = data["services"]["samuraibff"]["environment"]
            entries = json.loads(bff["SAMURAIBFF_FINAL_TRACKS_JSON"])
            mutation(entries)
            bff["SAMURAIBFF_FINAL_TRACKS_JSON"] = json.dumps(entries)
            with self.assertRaises(ValueError):
                validate(data)


if __name__ == "__main__":
    unittest.main()
