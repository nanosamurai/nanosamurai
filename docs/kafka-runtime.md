# Kafka runtime security update

The broker and topic initializer currently pin Apache Kafka 4.3.1 by digest and
set `-XX:-UseBASE64Intrinsics`. This is the interim mitigation for
[CVE-2026-114938](https://access.redhat.com/security/vulnerabilities/RHSB-2026-018);
the pinned upstream image still contains an older JVM. Additional JVM options
can be supplied through `KAFKA_JAVA_TOOL_OPTIONS`; Compose appends the mitigation
without changing Kafka's separate heap, authentication or performance options.

## Fixed runtime recipe

[`docker/kafka/Dockerfile`](../docker/kafka/Dockerfile) preserves Apache Kafka
4.3.1's complete vendor distribution and replaces its entire Linux amd64/musl JRE
with Eclipse Temurin 21.0.13.1+2. The official release archive is verified against
its pinned SHA-256 before extraction. This is a fixed build identified by
[Adoptium](https://adoptium.net/news/2026/11/temurin-november-2026-cspu-java4shell),
not an assumption that updating Alpine packages updates Java.

The recipe retains the Kafka application version, CLI commands, configuration,
data formats, non-root user, vendor licenses and Temurin CA entrypoint. It
preserves the eMudhra truststore hardening and appends the Base64 mitigation to
caller JVM options as defense in depth. The image also sets the mitigation in
its default `JAVA_TOOL_OPTIONS`, covering direct commands that bypass its
entrypoint. Custom Java truststores require separate
review; importing additional system roots can change the default trust policy.

Apache's two pre-generated application CDS archives were built by the old JVM.
The installer removes `/opt/kafka/storage.jsa` and `/opt/kafka/kafka.jsa`, and
removes exactly their two `-XX:SharedArchiveFile=` arguments from the vendor
launch script. It fails if the expected launch layout changes. The remaining
launch/configuration behavior and complete Kafka JAR classpath are retained.

Build and qualify the supported Linux amd64 artifact:

```bash
docker build --platform linux/amd64 -t nanosamurai-kafka:qualified docker/kafka
python smoke-tests/kafka_runtime.py --image nanosamurai-kafka:qualified
```

The smoke uses its own Compose project, an internal network, synthetic messages
and a temporary named volume. It publishes no host ports and cleans up only its
own resources. It checks the JVM build, actual broker-start flags, caller-option
preservation, Java truststore and non-root execution. It runs the real Compose
topic initializer twice, recreates the broker, and verifies topic identity,
configuration and messages survive. This proves preservation only for its
explicitly mounted test volume, not for an existing evaluator installation.
It does not touch the normal local stack.

## Publication and promotion

Draft PRs run source checks without starting this workflow's image qualification.
Marking a PR ready for review triggers the build/runtime/scan gates. The Kafka
workflow builds and tests a candidate, generates an SPDX SBOM with Kafka inventory,
and requires both OS and Kafka Java package coverage in the complete image scan.
It collects all severities before applying the Unknown/High/Critical publication
gate. Full vulnerability reports are not uploaded publicly.
On reviewed `master` changes, it publishes the already-tested image bytes through
the repository's `GITHUB_TOKEN` to `ghcr.io/nanosamurai/kafka`, using
`sha-<commit>-4.3.1`. It does not rebuild after qualification. No personal access
token is required. The SBOM is attached as a signed registry attestation.

For the first publication, confirm the package is linked to this repository and
public. The workflow verifies anonymous manifest access before promotion can
be accepted. Source preparation alone does not establish a published fixed
image. Until qualification/publication is complete, the runnable Compose
defaults retain the upstream digest with the explicit mitigation. Promoting the
fixed registry digest is a separate reviewed pin change after the same checks
pass against the published artifact.

## Existing installations

**Stop before recreating an existing broker.** Changing an image or environment
can recreate the container and destroy data stored in its writable layer.
The current Compose file has no explicit broker data mount or `KAFKA_LOG_DIRS`.
Standard existing installations were found with Kafka metadata under
`/tmp/kafka-logs`, outside the image's declared `/var/lib/kafka/data` volume.
Preserving the image's anonymous volumes therefore does not prove preservation
of Kafka data. Storage layout is unchanged by this update.

Before any image or mitigation rollout to an existing installation:

1. Use the existing checkout, Compose project and file list to identify the
   broker, including stopped containers: `docker compose ps --all -q broker`.
   Record its image/version and inspect its actual mounts with
   `docker inspect --format '{{json .Mounts}}' CONTAINER_ID`.
2. Copy `/opt/kafka/config/server.properties` from that container into a protected
   backup directory outside Git; do not print the configuration because custom
   deployments can contain credentials. Check the effective `log.dirs`/`log.dir`
   and `metadata.log.dir`, including any custom startup configuration. Verify
   every data directory is actually covered by a mount. Do not infer this from
   `VOLUME` declarations or an empty `/var/lib/kafka/data` mount.
3. Drain producers/consumers, then stop the broker through its existing Compose
   configuration. Retain the stopped container, exact image and all volumes.
   Copy **all** log and metadata directories from the stopped container into
   protected backup storage. For an installation confirmed to use
   `/tmp/kafka-logs`, `docker cp CONTAINER_ID:/tmp/kafka-logs /secure/backup/kafka-logs`
   copies that directory without removing the original. Replace the destination
   with an actual protected directory; include separate metadata directories and
   configuration where configured. Backups can contain sensitive event data.
4. **Do not proceed to `compose up`, `--force-recreate`, `rm` or `down`.** An
   installation using the writable layer first needs a reviewed storage migration:
   restore a copy into persistent storage, configure that exact directory, and
   validate the original cluster identity, topic IDs, records and committed
   consumer offsets in isolation before switching. Retain the original stopped
   container and verified backup until acceptance. Creating an empty volume or
   rerunning the topic initializer does not restore records or consumer offsets.

The storage migration is a separate acceptance gate and is not implemented or
validated by this JVM source preparation. Consequently there is no generic
existing-broker recreation command here. A different Kafka version selected by
an override also requires compatibility review; do not downgrade its data to
4.3.1. Keep `COMPOSE_BIND_IP=127.0.0.1`, and never reset volumes for a JVM update.
