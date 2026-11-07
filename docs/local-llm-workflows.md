# Local LLM workflows

A workflow runs a prompt over a finished transcript, for example to write a
summary or a list of action items. The optional `docker-compose.llm.yml`
overlay runs workflows on a local model. Transcripts and results stay on your
machine.

The overlay adds:

| Service | Role |
| --- | --- |
| `ollama` | Serves the model through an OpenAI-compatible API. |
| `ollama_pull` | One-shot job: downloads the model on first start. |
| `workflow-runner` | Takes workflow jobs from Kafka, calls Ollama, and writes the result. |

It also turns on workflows in the BFF and result storage in the persistor.
Workflows run on demand: you start one on a finished recording. Community
Edition does not run workflows automatically while you record, and it has no
webhook delivery.

> The workflow runner image is not published yet. Until it is, the overlay's
> default image is a placeholder (`sha-unpublished`) and the pull fails. Set
> `WORKFLOW_RUNNER_IMAGE` in `.env` to an image you built, or wait for the
> release pin. See [Image release policy](image-release-policy.md).

## Before you start

Start the default stack once with [Getting started](getting-started.md).

The default model is
[Qwen2.5 7B Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)
(Apache 2.0), as the 4-bit Ollama build `qwen2.5:7b-instruct`. The first start
downloads about 5 GB into the `nanosamurai_ollama_models` volume.

To use another model, set `WORKFLOW_LLM_MODEL` in `.env` to an
[Ollama library](https://ollama.com/library) tag. The overlay downloads it and
the runner accepts only that model.

## Hardware

Ollama uses the GPU when it has free memory. If the model does not fit, Ollama
runs some or all of it on the CPU. That works, but a summary can take minutes.

A 7–8B model at 4-bit with the default 16k-token context is expected to need
about 5–6 GB of GPU memory. It should fit next to the default speech models on
a 16 GB GPU. This is not measured yet.

Ollama unloads the model 5 minutes after the last request (`OLLAMA_KEEP_ALIVE`).
`OLLAMA_CONTEXT_LENGTH` (default `16384` tokens) limits how much transcript the
model reads. A longer context uses more memory.

## Start

Add the overlay after `docker-compose.yml` and any model overlays:

```bash
docker compose -f docker-compose.yml -f docker-compose.llm.yml pull
docker compose -f docker-compose.yml -f docker-compose.llm.yml up -d
docker compose -f docker-compose.yml -f docker-compose.llm.yml logs -f ollama_pull workflow-runner
```

`ollama_pull` exits with code 0 when the model is ready. Later starts skip the
download. Use the same file list for `down` and later `up -d` commands.

## Create a workflow

1. Open the **Workflows** page in the browser UI.
2. Create a workflow:
   - Source: the final transcript, track `parakeet` (or another final track
     you run).
   - Provider: `openai_compatible`.
   - Model: the value of `WORKFLOW_LLM_MODEL`, for example
     `qwen2.5:7b-instruct`.
   - Prompt: for example *Summarize this meeting in five bullet points and
     list the action items with their owners.*
3. Save it.

The editor offers only the providers the overlay enables. The runner rejects
any model that is not `WORKFLOW_LLM_MODEL`.

## Run it on a recording

1. Open a saved session with a final transcript.
2. In its **Workflows** panel, pick your workflow under **Run workflow**.
   The transcript source defaults to the workflow's own track; you can pick
   another stored track, for example to run a refined-transcript workflow on
   the final transcript.
3. Choose **Run**.

The result appears in the session when the model finishes. API clients can
start the same run with
`POST /api/recordings/{id}/workflows/{workflow_id}/runs`.

If no result appears, check the runner log:

```bash
docker compose -f docker-compose.yml -f docker-compose.llm.yml logs --tail=100 workflow-runner ollama
```

Failed attempts are retried and then written to Kafka topic
`workflow.dispatch.dlq`.

## Security

- Transcripts go only to the local Ollama service. The overlay sets
  `OLLAMA_NO_CLOUD=1`, so Ollama does not forward prompts to cloud models.
- Neither Ollama nor the runner publishes a host port.
- The runner is only on the internal `workflow` network with Kafka and
  Ollama. It has no internet access.
- Ollama is also on the default network, because it downloads models. Other
  stack services can reach it there, and it has internet access. After the
  download you can leave it as is: no host port is published.
- The model endpoint and the allowed model come from the overlay, not from
  workflow definitions. A workflow cannot point the runner at another URL.
- Treat model output as untrusted text. The UI renders results as Markdown
  without raw HTML. Check results before you act on them.
- The overlay sets `SAMURAIBFF_WORKFLOWS_ENABLED=true`. This turns on
  workflow definitions and on-demand runs while the BFF stays in Community
  Edition mode, so webhooks stay off.
