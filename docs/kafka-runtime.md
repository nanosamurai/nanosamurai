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
caller JVM options as defense in depth. Custom Java truststores require separate
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
configuration and messages survive. It does not touch the normal local stack.

## Publication and promotion

The Kafka workflow builds and tests a candidate, generates a nonempty SPDX SBOM,
and scans the complete image. Unapproved High/Critical findings fail publication.
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

Drain active work and record the current image, Kafka version, data location
and topic state before replacing the broker. Keep the existing Compose project,
containers and volumes. An override may select another Kafka version; do not
downgrade existing data to 4.3.1. Choose a matching reviewed image and retain the
mitigation until its upgrade path is qualified.

After checking data preservation and selecting a qualified image, use the normal
checkout and the same file list as the existing stack:

```bash
docker compose pull broker kafka_init
docker compose up -d --no-deps broker
docker compose run --rm --no-deps kafka_init
```

Keep `COMPOSE_BIND_IP=127.0.0.1`. Do not run `down -v`, remove the existing broker
container or reset data as part of a JVM update. No database migration, Kafka
major upgrade or topic/consumer-group reset is required.
