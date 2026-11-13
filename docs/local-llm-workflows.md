# Local LLM workflows

A workflow runs a prompt over a finished transcript, for example to write a
summary or a list of action items. Workflows are part of the default stack:
you create them on the **Workflows** page and run them on demand on a finished
recording. With a local model, transcripts and results stay on your machine.

Community Edition runs workflows only when you start them. It does not run
workflows automatically while you record, and it has no webhook delivery.

## How it fits together

| Part | Role |
| --- | --- |
| SamuraiBFF | Stores workflow definitions and, when you run one, writes a job to Kafka topic `workflow.dispatch`. |
| `workflow-runner` | Takes the job, calls an OpenAI-compatible model server, and writes `workflow.result` and `workflow.outcome`. Part of `docker-compose.yml`. |
| SamuraiPersistor | Stores the result and each attempt's outcome in PostgreSQL. |
| Model server | Not part of the default stack: Ollama on your computer, Ollama in the stack (overlay), or another OpenAI-compatible server. |

The runner starts even when no model server is reachable. A run then fails
after 3 attempts, about 2 minutes, with `PROVIDER_UNAVAILABLE`.

## Choose where the model runs

| Option | Use it when |
| --- | --- |
| [Ollama on your computer](#ollama-on-your-computer) (default) | You already use Ollama or want to manage models yourself. |
| [Ollama in the stack](#ollama-in-the-stack) | You want Compose to download and run the model. |
| [Another server](#another-openai-compatible-server) | You run vLLM, the llama.cpp server or another OpenAI-compatible API. |

### Ollama on your computer

The default stack calls Ollama at `http://host.docker.internal:11434/v1`.

1. Install [Ollama](https://ollama.com/download) and start it. Keep its
   default address, `127.0.0.1:11434`.
2. Download the default model:

   ```bash
   ollama pull qwen2.5:7b-instruct
   ```

3. Start or restart the stack as in [Getting started](getting-started.md).

**Windows and macOS with Docker Desktop:** this works without other changes.
Docker Desktop forwards `host.docker.internal` to services that listen only on
`127.0.0.1`, so Ollama is not exposed to your network.

**Linux with Docker Engine:** the stack maps `host.docker.internal` to the
Docker host gateway, but Ollama's default `127.0.0.1` address is not reachable
from containers. Make Ollama listen on the Docker bridge address as well, for
example with `systemctl edit ollama`:

```ini
[Service]
Environment="OLLAMA_HOST=172.17.0.1:11434"
```

Check the address with `ip -4 addr show docker0`. Do not use `0.0.0.0` on a
machine that other computers can reach, unless a firewall blocks port 11434.
This Linux setup is not tested yet.

Ollama on your computer uses its own settings. Its default context window can
be shorter than a long transcript; Ollama then drops the start of the prompt.
Set the context length in the Ollama app settings, or set the
`OLLAMA_CONTEXT_LENGTH` environment variable (for example `16384`) before you
start Ollama.

### Ollama in the stack

The `docker-compose.ollama.yml` overlay adds:

| Service | Role |
| --- | --- |
| `ollama` | Serves the model inside the stack. Uses the GPU when it has free memory. |
| `ollama_pull` | One-shot job: downloads `WORKFLOW_LLM_MODEL` on first start. |

It also points the runner at `http://ollama:11434/v1`. Add it after
`docker-compose.yml` and any model overlays:

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml pull
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d
docker compose -f docker-compose.yml -f docker-compose.ollama.yml logs -f ollama_pull workflow-runner
```

The first start downloads about 5 GB into the `nanosamurai_ollama_models`
volume. `ollama_pull` exits with code 0 when the model is ready; later starts
skip the download. Use the same file list for `down` and later `up -d`
commands. Stop an Ollama on your computer first if it uses the same GPU.

`OLLAMA_CONTEXT_LENGTH` (default `16384` tokens) limits how much transcript the
model reads, and `OLLAMA_KEEP_ALIVE` (default `5m`) how long an idle model
stays in GPU memory.

### Another OpenAI-compatible server

Set the server's base URL and model in `.env`:

```bash
WORKFLOW_LLM_BASE_URL=http://host.docker.internal:8001/v1
WORKFLOW_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
```

The runner sends `POST {WORKFLOW_LLM_BASE_URL}/chat/completions`. The default
stack sends no API key.

## Choose a model

The default model is
[Qwen2.5 7B Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)
(Apache 2.0), as the 4-bit Ollama build `qwen2.5:7b-instruct`.

`WORKFLOW_LLM_MODEL` in `.env` is the runner's allow-list: a comma list of
model IDs, for example `qwen2.5:7b-instruct,gemma3:12b`. A workflow whose model
is not in the list fails with `MODEL_NOT_ALLOWED` before any model call. The
in-stack overlay downloads only a single model, so use one ID there.

Reasoning models (for example `qwen3` or `gpt-oss`) count their thinking
toward `max_tokens`. When the thinking uses all of it, the run fails with
`PROVIDER_BAD_RESPONSE` and `finish_reason=length`. Raise `max_tokens` in the
workflow's parameters or choose an instruct model.

## Hardware

Ollama uses the GPU when it has free memory. If the model does not fit, Ollama
runs some or all of it on the CPU. That works, but a summary can take minutes.

A 7–8B model at 4-bit with a 16k-token context is expected to need about
5–6 GB of GPU memory. It should fit next to the default speech models on a
16 GB GPU. This is not measured yet. A run that takes longer than
`WORKFLOW_RUNNER_OPENAI_TIMEOUT_S` (default 300 seconds) is retried.

## Create a workflow

1. Open the **Workflows** page in the browser UI.
2. Create a workflow:
   - Source: the final transcript, track `parakeet` (or another final track
     you run).
   - Provider: **Self-hosted LLM (OpenAI-compatible API)**.
   - Model: a model from `WORKFLOW_LLM_MODEL`, for example
     `qwen2.5:7b-instruct`.
   - Prompt: for example *Summarize this meeting in five bullet points and
     list the action items with their owners.*
3. Save it.

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
docker compose logs --tail=100 workflow-runner
```

A failed run is retried after 10 seconds and 2 minutes
(`WORKFLOW_MAX_ATTEMPTS`, default 3), then stored as failed and written to
Kafka topic `workflow.dispatch.dlq`.

## Settings

| Setting (`.env`) | Default | Meaning |
| --- | --- | --- |
| `WORKFLOW_LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | Model server base URL. The overlay sets its own. |
| `WORKFLOW_LLM_MODEL` | `qwen2.5:7b-instruct` | Allowed model IDs (comma list). |
| `WORKFLOW_RUNNER_OPENAI_TIMEOUT_S` | `300` | Timeout per model call, in seconds. |
| `WORKFLOW_MAX_ATTEMPTS` | `3` | Attempts per run before it fails. |
| `SAMURAIBFF_WORKFLOWS_ENABLED` | `true` | `false` hides workflows in the UI and API. Stop `workflow-runner` too if you don't need it. |

The BFF offers only the `openai_compatible` provider in the workflow editor
(`SAMURAIBFF_WORKFLOW_PROVIDER_TYPES`). The persistor stores workflow results
and outcomes, but no webhook outcomes.

## Security

- Transcripts go to the model server you configure. With Ollama on your
  computer or in the stack they stay on your machine. The overlay sets
  `OLLAMA_NO_CLOUD=1`, so its Ollama does not forward prompts to cloud models;
  for Ollama on your computer, check its own cloud settings.
- Neither the runner nor the in-stack Ollama publishes a host port.
- In the default stack the runner is on the default Compose network so that it
  can reach `host.docker.internal`; that network also has internet access.
  With `docker-compose.ollama.yml` the runner is only on the internal
  `workflow` network with Kafka and Ollama, with no internet access.
- The model endpoint and the allowed models come from Compose settings, never
  from workflow definitions. A workflow cannot point the runner at another URL.
- Any user who can read a session can run workflows on it, with no rate limit.
  Each run uses the model server, and the latest result of a workflow replaces
  the previous one for every reader of the session.
- Treat model output as untrusted text. The UI renders results as Markdown
  without raw HTML. Check results before you act on them.
