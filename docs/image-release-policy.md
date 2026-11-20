# Image release policy

The Compose defaults use immutable `sha-<full-git-sha>` tags for all nanosamurai
service images. A pin identifies both the service source revision and the image
that passed its publication workflow. These checked-in pins are the primary
image-selection mechanism for the evaluator. Image environment variables are
optional overrides for local development, evaluation of another immutable
release, or rollback; users do not need to set them for the normal quickstart.

Keep local source-build image selections and enrollment calibration in the
ignored `.env` or `docker-compose.local-asr.yml`, selected explicitly with `-f`.
Do not commit these machine-local overrides or promote newly built images into
the default pins as part of provider development. The base stack, the Whisper
overlay, and the Qwen realtime overlay use release pins. The Qwen worker overlay
has only a source-build recipe; promoting it requires a separate release change
after the checks below. The base stack's `workflow-runner` uses a release pin
like the other services; the Ollama overlay uses an explicit Ollama version.

Before updating a default pin:

1. Confirm CI and the image-publication workflow succeeded for the source SHA.
2. Pull the exact tag from GHCR.
3. Validate the default Compose model and the observability override.
4. Run the applicable smoke-test tiers.
5. Verify the package can be pulled anonymously before announcing the release.
6. Update the rollout record with the tested SHAs and known limitations.

Infrastructure images use explicit version tags rather than `latest`. Automated
dependency updates must still pass the same Compose and smoke validation.

Future stable releases may add semantic-version tags. An `edge` tag may be
provided for convenience, but it must never be the default in this repository.

## Kafka JVM patch

The inspected Linux amd64 `apache/kafka:4.3.2` image still bundles Temurin
21.0.12.1+1. A Kafka tag bump alone does not fix
[CVE-2026-114938](https://adoptium.net/news/2026/11/temurin-november-2026-cspu-java4shell/).
The temporary `docker/kafka` recipe installs checksum-pinned Temurin 21.0.13.1+2
into the complete Kafka 4.3.2 distribution and removes startup archives tied to
the old JVM. It retains the existing user, certificates policy and licenses.

```sh
docker build --platform linux/amd64 -t kafka:qualified docker/kafka
python smoke-tests/kafka_runtime.py --image kafka:qualified
```

The reusable smoke checks startup, the actual JVM/mitigation, and preservation
of records, topic configuration and committed offsets across replacement. It
uses an isolated project and disposable volume, with no host ports. It checks
compatibility; the vendor build/version establishes the JVM security fix.
The workflow builds once, tests and scans that image, then publishes those same
bytes to `ghcr.io/nanosamurai/kafka` on `master`. Promote only its verified,
anonymously pullable registry digest. Until then, Compose retains the pinned
upstream image with `-XX:-UseBASE64Intrinsics` (mitigated, not patched).

**Existing installations:** default Kafka data can be in `/tmp/kafka-logs` in
the container's writable layer. Before any recreation, stop/drain the broker,
back up all configured log and metadata directories, and verify a persistent
storage migration. Retain the old container and backup; an empty volume or
rerunning topic initialization does not recover records or committed offsets.
The disposable-volume smoke does not validate an existing installation's storage.

Future patches should update versions/checksums/digests and reuse these checks,
not add another test harness or incident runbook. Once an official image has a
verified fixed JVM, switch back to its digest and retire the temporary image
recipe and publisher. Keep release-specific test results in the PR/issue.
