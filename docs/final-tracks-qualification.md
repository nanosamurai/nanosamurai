# Final-track spike qualification — 2026-09-10

The finalizer-first local spike passed its integrated Kafka/S3/PostgreSQL smoke.
Full Phase 3 remains open for windowed refinement, a materially different real
profile and its remaining platform criteria.

| Check | Result |
| --- | --- |
| Real WhisperX + VAD + Czech alignment + pyannote | Six segments; actual word timing and speaker labels; no degradation |
| Three-second generated silence | Successful empty transcript, `no_speech` |
| Independent tracks | Real primary success, synthetic secondary success, synthetic terminal failure after three attempts |
| Shared source / SQL | One recording, three outcome rows, one primary transcript per completed session |
| Replica distribution | Two source partitions observed on two replicas of the same synthetic track/group |
| Replay | Canonical bytes, result/attempt identities and SQL counts unchanged; no reinference |
| Database outage | Canonical offsets unchanged while unavailable; caught up after restart without duplicates |
| Process exit | One-shot process exited after durable S3 manifest and before Kafka publication; restarted group published exactly the accepted bytes |
| Compatibility | Existing primary body and recording Range API work; full BFF suite covers feature-off refined, final API, authentication and WS paths |
| Rejection / degradation | Frozen-plan and source/tenant tampering, unknown profiles, retention rejection, storage failure, missing Kafka key and missing timing/speaker enrichment covered |

Validation suites: BFF **129 tests / 962 assertions**, Persistor **16 tests / 90
assertions**, Python **128 passed / 11 deselected** for `-m 'not integration'`,
including **17 final-track contract/replay tests**. UI release build and both
Java 21 service JAR builds succeeded. Python and Java share a synthetic
protobuf/header identity vector. The complete native Windows Python selection
was attempted but crashes in the existing realtime faster-whisper native model
initialization (`0xc06d007f`); it is not reported as passing. Real speech/model
qualification and the complete new asynchronous flow ran in the Linux images.

Measured on an RTX 5090 Laptop GPU using a consented 20-second Czech fixture:

| Run | Initialization + processing | Subsequent processing |
| --- | ---: | ---: |
| Existing WhisperX function, same cached runtime | 16.657 s | 1.502 s |
| New worker, latest integrated run | 16.171 s | 1.459 s |

Both paths produced six segments, with the baseline reporting 31 aligned words
and six speaker-labelled segments. These are small-fixture compatibility
observations, not quality or throughput benchmarks. The earlier first model
qualification took 103.145 seconds while loading/validating its model assets.
Do not compare that first-cache run with warm inference.

The new worker recorded queue waits of 0.020 s and 16.668 s for the two real
jobs; one model execution per worker makes the second recording wait. The
synthetic successful track recorded approximately 1.005 s processing time.
PyTorch peak allocated GPU memory was **2,976,341,504 bytes**; this excludes
CTranslate2 allocations and is not total GPU memory. Individual VAD/ASR/
alignment/diarization timings are not instrumented in the inherited composite;
stage completion and total processing are recorded explicitly.

Qualification images were assembled from existing local service runtime layers
with the current source or newly built JARs. The pinned speech runtime was
verified: WhisperX 3.8.6, faster-whisper 1.2.1, pyannote.audio 4.0.7, torch and
torchaudio 2.8.0+cu128, transformers 4.57.6 and huggingface-hub 0.36.2. The
repository Dockerfiles support fresh builds; this report does not claim that
every upstream runtime layer was rebuilt from scratch.

No secrets, fixture audio, transcript artifacts or full execution reports were
committed. New event/SQL identities and exact configured storage scopes prevent
cross-session/source substitution. All published test ports use loopback. The
evaluation uses retained isolated fixtures; coordinated retention/deletion and
recording assembly recovery remain prerequisites for wider use.
