# Smoke tests and release rehearsal

The tests are cumulative: each higher tier requires the services exercised by
the lower tiers.

| Tier | What it verifies |
| --- | --- |
| 1 | BFF HTTP connectivity |
| 2 | WebSocket and realtime ASR |
| 3 | Session audio reaches Kafka |
| 4 | Recording, refined, or final async signal |

Tier 2 accepts the first realtime partial by default. Pass `--require-final`
when validating a native-streaming provider to prove that closing the audio
WebSocket flushes a terminal event through BFF. Pass
`--require-tracks faster-whisper,qwen` with the Qwen override to require a
matching event from both peer services.

## Install the test environment

```bash
python -m venv .venv-smoke
. .venv-smoke/bin/activate
python -m pip install -r utilities/k8s_local_smoke_test/requirements.txt
python -m pip install -r utilities/k8s_local_smoke_test/requirements.kafka.txt
```

On Windows PowerShell, use `py -m venv .venv-smoke` and invoke
`.\.venv-smoke\Scripts\python` for the remaining commands.

## Release rehearsal

1. Copy `.env.example` to `.env` and set a least-privilege `HF_TOKEN`.
2. Run `docker compose config --quiet`.
3. Run `docker compose pull` and then `docker compose up -d`.
4. Wait for the speech services and their models to finish starting.
5. Run Tier 1, Tier 2, Tier 3, Tier 4 `recording-finished`, and Tier 4
   `refined`.
6. Run strict Tier 4 `final` when validating the full finalizer contract.
7. Repeat `docker compose up -d` without deleting volumes and verify the
   migration and seed jobs complete successfully.
8. Start the observability override and repeat Tier 3/4 while checking Tempo,
   Prometheus, Loki, and Grafana.

Use `smoke-tests/smoke.sh` or `smoke-tests/smoke.ps1` to orchestrate the tiers.
Tier 4 `final` remains opt-in because model and alignment cold starts can be
long. A release note must state clearly if that signal is not validated.

The test audio is synthetic repository data. Never add customer recordings,
transcripts, tokens, or identifying metadata to test fixtures or public issues.
