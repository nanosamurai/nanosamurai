# Contributing

This repository is the public front door for the nanosamurai Community Edition.

Before opening a pull request:

- keep secrets out of git
- run `docker compose config`
- run the Tier 1 smoke test when changing Compose or runtime docs
- document user-facing runtime changes in `README.md` or `docs/`

For local checks:

```bash
python -m venv .venv-smoke
. .venv-smoke/bin/activate
python -m pip install -r utilities/k8s_local_smoke_test/requirements.txt
python utilities/k8s_local_smoke_test/tier1_bff_connectivity.py --base-url http://127.0.0.1:8000
```
