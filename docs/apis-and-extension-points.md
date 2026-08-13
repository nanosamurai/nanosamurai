# APIs and extension points

SamuraiBFF is the public API and browser boundary for the Nanosamurai stack.
This guide identifies the entry points and their owning documentation without
duplicating the complete contracts.

## HTTP API

When the evaluator stack is running:

- Swagger UI: <http://127.0.0.1:8000/docs>
- Canonical OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>
- REST API base: <http://127.0.0.1:8000/api>

SamuraiBFF generates `GET /openapi.json` from its route and schema definitions
at runtime. It is the canonical machine-readable REST contract for the running
image; the BFF repository does not currently commit a static OpenAPI document.
The customer-facing OpenAPI surface includes browser authentication and
tenant-scoped `/api/*` routes. It intentionally excludes internal callbacks,
WebSockets, SPA routes, and operational probes.

For a repository-owned overview that can be read without starting the service,
see the
[SamuraiBFF API documentation](https://github.com/nanosamurai/samuraibff/blob/master/docs/api.md).
Detailed endpoint schemas and responses should be read from the generated
OpenAPI contract rather than duplicated here.

## Realtime WebSockets

Realtime transcription uses two connections:

```text
GET /ws/events?session_id=<uuid>
GET /ws/audio?session_id=<uuid>&lang=<code>&sample_rate=16000
```

- `/ws/audio` receives binary PCM16LE mono audio, normally at 16 kHz.
- `/ws/events` sends JSON status, error, realtime, refined, and enabled
  extension events.
- Authenticated deployments require a bearer token during both WebSocket
  upgrades.
- A session must belong to the authenticated tenant when authentication is
  enabled.

WebSockets are intentionally outside OpenAPI. See the complete
[SamuraiBFF WebSocket contract](https://github.com/nanosamurai/samuraibff/blob/master/docs/ws-contract.md)
for lifecycle, close codes, event shapes, and ordering semantics.

## Python SDK and CLI

Until a reviewed release is published to PyPI, install the SDK from the
audited Git commit pinned below:

```bash
python -m pip install "git+https://github.com/nanosamurai/nanosamurai-sdk.git@ec5797be2364837e7c7e9dd17644fde60fa7c61a"
```

Pin deployments to a reviewed commit or release tag rather than a mutable
branch. Do not install similarly named packages from PyPI.

The SDK currently targets authenticated machine-to-machine integrations. In an
authentication-enabled SamuraiBFF deployment, create a credential from the
browser UI's **API Credentials** page and copy the show-once client secret. The
page creates a Keycloak OAuth client; Keycloak then issues short-lived bearer
tokens through `client_credentials`. See
[Create a credential in the BFF UI](authentication.md#create-a-credential-in-the-bff-ui)
for the required Keycloak admin setup and complete flow. Then set:

```bash
export NANOSAMURAI_API_URL=https://your-nanosamurai.example
export NANOSAMURAI_ISSUER=https://your-auth.example/realms/nanosamurai
export NANOSAMURAI_CLIENT_ID=<client-id>
export NANOSAMURAI_CLIENT_SECRET=<client-secret>
```

Windows PowerShell:

```powershell
$env:NANOSAMURAI_API_URL = "https://your-nanosamurai.example"
$env:NANOSAMURAI_ISSUER = "https://your-auth.example/realms/nanosamurai"
$env:NANOSAMURAI_CLIENT_ID = "<client-id>"
$env:NANOSAMURAI_CLIENT_SECRET = "<client-secret>"
```

Transcribe a compatible WAV file:

```bash
nanosamurai transcribe wav path/to/audio.wav --lang en --sample-rate 16000
```

The helper validates mono 16-bit PCM WAV input. The complete installation,
Python, CLI, and stream-control examples live in the
[Nanosamurai SDK repository](https://github.com/nanosamurai/nanosamurai-sdk).

The default Compose evaluator disables authentication for a quick localhost
evaluation and does not provision M2M credentials. Use the browser or public
smoke-test clients for that configuration; do not pretend production
credentials exist in the evaluator stack. Authenticated deployments must bring
their own Keycloak; see
[Authentication and bring-your-own Keycloak](authentication.md) for browser
client setup, required token claims, M2M provisioning, and the limitations of
other OIDC providers.

## Agentic workflow and webhook contracts

The public code contains contracts and integration points for external agentic
workflow and webhook services. Community Edition does not ship those execution
or delivery services, and its default feature flags keep the corresponding
runtime lanes disabled.

This boundary lets users implement compatible services without making a
nonexistent runner part of the default evaluator experience.

### Workflow integration

An external workflow service can consume session/transcript data and publish
JSON results to Kafka topic `workflow.result`. When enabled, SamuraiBFF routes
results to the originating browser as `/ws/events` messages, and
SamuraiPersistor can store workflow result and outcome records.

The owning public description is
[SamuraiBFF webhooks and workflows](https://github.com/nanosamurai/samuraibff/blob/master/docs/features-webhooks-workflows.md).

### Webhook integration

Public schemas include session-scoped webhook routing and audit/persistence
contracts. A user-supplied delivery service is responsible for outbound HTTP,
authentication, retry behavior, SSRF protection, allowlisting, rate limiting,
and delivery outcomes.

Nanosamurai Community Edition does not provide or enable that network egress
service.

## Explicit opt-in

Only enable the extension lanes after supplying compatible services, Kafka
topics, security controls, and operational ownership:

```text
SAMURAIBFF_CE_MODE=false
SAMURAIPERSISTOR_CE_MODE=false
```

Setting these flags does not install a workflow runner or webhook dispatcher.
It enables the BFF APIs, routing consumers, and persistence consumers that are
disabled in the default Community Edition mode.

SamuraiPersistor also supports per-consumer controls outside CE mode:

```text
SP_WEBHOOK_OUTCOME_ENABLED
SP_WORKFLOW_RESULT_ENABLED
SP_WORKFLOW_OUTCOME_ENABLED
```

Enable only the topics and consumers implemented by the supplied integration.
Missing services or topics can otherwise create failed or misleading runtime
flows.

## Component ownership

- SamuraiBFF owns the REST, WebSocket, browser, authentication, session, and
  extension-routing contracts.
- Xamurai owns the gRPC speech service and Kafka speech-worker behavior.
- Nanosamurai SDK owns client authentication and convenience APIs.
- SamuraiPersistor owns PostgreSQL persistence of transcript and enabled
  extension events.
- This repository owns the supported public Compose evaluation path.

See [Transcription lifecycle](transcription-lifecycle.md) for the speech data
flow and [Deployment and security boundaries](deployment-and-security.md)
before exposing any interface beyond localhost.
