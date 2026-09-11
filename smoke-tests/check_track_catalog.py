"""Validate catalog/worker agreement in resolved Compose JSON without printing secrets.

Pipe `docker compose ... config --format json` into this script before startup.
This checks deployment configuration, not running worker health.
"""

import json
import sys


def validate(compose):
    """Raise ValueError on unsafe exposure or an unmatched catalog identity."""
    services = compose["services"]
    bff = services["samuraibff"]["environment"]
    for service in services.values():
        for port in service.get("ports", []):
            if port.get("published") and port.get("host_ip") not in ("127.0.0.1", "::1"):
                raise ValueError("Published test ports must bind to loopback")
    for stage, prefix in (("refined", "REFINEMENT"), ("final", "FINAL")):
        if bff.get(f"SAMURAIBFF_{prefix}_TRACKS_ENABLED") != "true":
            continue
        catalog = json.loads(bff[f"SAMURAIBFF_{prefix}_TRACKS_JSON"])
        workers = [service.get("environment", {}) for name, service in services.items()
                   if name != "samuraibff"]
        if not 1 <= len(catalog) <= 4 or len({entry["track_id"] for entry in catalog}) != len(catalog):
            raise ValueError("Catalog must contain one to four unique track IDs per stage")
        if sum(entry["primary"] for entry in catalog) != 1:
            raise ValueError("Each enabled stage requires exactly one primary")
        for entry in catalog:
            if entry["primary"] and not entry.get("default_selected", True):
                raise ValueError("The configured primary must be selected by default")
            matches = [worker for worker in workers
                       if worker.get(f"{prefix}_TRACK_ID") == entry["track_id"]
                       and worker.get(f"{prefix}_PROFILE_ID") == entry["profile_id"]
                       and worker.get("ASR_TRACK_STAGE", "final") == stage]
            if not matches:
                raise ValueError(f"No matching {stage} worker for configured track {entry['track_id']}")
            if entry["profile_id"].startswith("test-"):
                gate = f"{prefix}_TRACK_TEST_PROFILE_ENABLED"
                if bff.get(f"SAMURAIBFF_{gate}") != "true" or any(worker.get(gate) != "true" for worker in matches):
                    raise ValueError("Synthetic profiles require explicit BFF and worker gates")


if __name__ == "__main__":
    try:
        validate(json.load(sys.stdin))
    except (ValueError, KeyError, TypeError):
        sys.exit("Track catalog validation failed: check stage/profile identities, primary, test gates and loopback ports.")
    print("Track catalog and worker configuration agree; published ports are loopback-only.")
