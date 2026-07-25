# Deployment and security boundaries

The public Nanosamurai repository supports a local Docker Compose evaluation
path. Its services are containerized and can be adapted to other environments,
but the repository does not ship production Kubernetes manifests, managed
infrastructure, or a turnkey air-gap bundle.

## Supported public path

The supported Community Edition quickstart is:

```bash
cp .env.example .env
docker compose pull
docker compose up -d
docker compose --profile speech up -d
```

All default service images are pinned to immutable source-SHA tags. Supporting
infrastructure images use explicit version tags. See
[Image release policy](image-release-policy.md).

## Kubernetes adaptability

The application services expose container, health, configuration, and
observability boundaries that can be mapped to Kubernetes. Operators who adapt
the stack must supply and own:

- manifests or charts
- secrets and identity integration
- persistent volumes and object storage
- Kafka and PostgreSQL lifecycle
- ingress, TLS, and network policies
- GPU scheduling and model caching
- autoscaling, disruption handling, and upgrades
- monitoring, backup, restore, and incident response

Do not interpret containerization as a claim that public Helm charts or a
supported production Kubernetes distribution are included.

## Isolated and air-gapped environments

Speech processing does not require a cloud speech API at runtime, but an
isolated installation must stage every external artifact before disconnecting:

- all pinned application and infrastructure container images
- selected Hugging Face speech, alignment, and diarization models
- accepted gated-model terms and the resulting model artifacts
- Python packages or smoke-test environments needed inside the boundary
- the OpenTelemetry Java agent when using the observability override

The normal connected quickstart downloads images, models, and the Java agent.
Copying `.env` and starting Compose is therefore not, by itself, a turnkey
air-gap installation procedure. Validate an offline start from an empty Docker
network and a pre-populated artifact cache before claiming a specific isolated
deployment is complete.

Pyannote telemetry is force-disabled by Xamurai to prevent unexpected outbound
metric export. Operators must still audit every image and dependency for their
own outbound-connectivity requirements.

## Localhost evaluator boundary

Compose publishes host ports through `COMPOSE_BIND_IP`, which defaults to
`127.0.0.1`. Keep that default.

The evaluator configuration:

- uses fixed development credentials
- disables browser/API authentication for quick local access
- runs LocalStack rather than production object storage
- exposes local diagnostic services

Do not change the bind to `0.0.0.0` as a shortcut. Before any shared or remote
deployment, enable authentication, replace credentials, add TLS, restrict
probes and metrics, and define network policy.

## Community Edition boundary

Included in the public evaluator:

- browser UI and SamuraiBFF API
- realtime transcription
- asynchronous refinement
- recording and final transcript processing
- transcript persistence and local recording storage
- Python SDK and CLI source
- public smoke tests
- optional local metrics, traces, and logs

Public contracts but disabled by default:

- agentic workflow routing and results
- webhook routing and delivery outcomes

Not supplied:

- workflow execution services
- webhook delivery services
- public production Kubernetes manifests
- cloud-account infrastructure automation
- production identity, backup, scaling, or operational support

Users can implement compatible workflow and webhook services and opt into the
public integration contracts. See
[APIs and extension points](apis-and-extension-points.md). Enabling the flags
without supplying the external services does not create a working integration.

## Data and credential handling

- Never commit `.env`, tokens, recordings, transcripts, enrollment samples, or
  customer data.
- Give Hugging Face tokens only the model-read access required.
- Prefer workload identity over static object-storage credentials outside the
  evaluator.
- Treat Kafka headers, gRPC metadata, workflow results, and webhook inputs as
  untrusted data.
- Keep health, readiness, metrics, Kafka, PostgreSQL, and object storage off
  public interfaces.
- Remove sensitive fields before posting logs or traces to a public issue.

## Known limitations

- No minimum hardware guarantee has been established; the July 2026 release
  rehearsal used a 24 GB RTX 5090 Laptop GPU.
- Full speech processing requires an NVIDIA runtime in the supplied profile.
- Model cold starts and final alignment may take several minutes.
- Async Python workers do not yet provide dedicated Prometheus metrics.
- The realtime gRPC trace is not yet joined to the deterministic session/Kafka
  trace.
- The public repository does not yet provide a tested artifact-export command
  for turnkey air-gapped installation.

For vulnerability reports, follow [SECURITY.md](../SECURITY.md). For evaluator
problems, collect only the non-sensitive diagnostics described in
[Troubleshooting](troubleshooting.md).
