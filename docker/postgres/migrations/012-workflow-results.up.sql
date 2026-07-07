-- Vendored from samuraipersistor/resources/migrations/004-workflow-results.up.sql
--
-- Migration: persist RFC-0003 workflow results produced by workflow-runner.
--
-- Design:
-- - workflow_results_history: append-only event log (non-incremental triggers)
-- - workflow_results_latest: one row per (session_id, workflow_id) for fast UI reads

CREATE TABLE IF NOT EXISTS workflow_results_history (
    id                     uuid PRIMARY KEY,
    created_at             timestamptz NOT NULL,

    workflow_run_id         uuid NOT NULL,
    tenant_id              uuid NOT NULL,
    session_id             uuid NOT NULL,
    workflow_id            uuid NOT NULL,

    trigger_type            text NULL,
    trigger_source_event_id text NULL,

    status                 text NOT NULL,

    render_markdown        text NULL,
    render_json            jsonb NULL,

    provider_type          text NULL,
    provider_model_id      text NULL,

    usage_input_tokens     integer NULL,
    usage_output_tokens    integer NULL,

    stream_source_uri      text NULL,
    stream_source_node_id  text NULL,

    error_code             text NULL,
    error_detail           text NULL,

    kafka_topic            text NULL,
    kafka_partition        integer NULL,
    kafka_offset           bigint NULL
);

-- Idempotency under Kafka redeliveries.
DO $$
BEGIN
  ALTER TABLE workflow_results_history
    ADD CONSTRAINT workflow_results_history_run_uniq
    UNIQUE (workflow_run_id);
EXCEPTION
  WHEN duplicate_object THEN
    NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_workflow_results_history_session_workflow_created_at
    ON workflow_results_history (session_id, workflow_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_workflow_results_history_tenant_created_at
    ON workflow_results_history (tenant_id, created_at DESC);


CREATE TABLE IF NOT EXISTS workflow_results_latest (
    session_id             uuid NOT NULL,
    workflow_id            uuid NOT NULL,

    -- copy of last observed result
    created_at             timestamptz NOT NULL,
    workflow_run_id        uuid NOT NULL,
    tenant_id              uuid NOT NULL,

    trigger_type            text NULL,
    trigger_source_event_id text NULL,
    status                 text NOT NULL,

    render_markdown        text NULL,
    render_json            jsonb NULL,

    provider_type          text NULL,
    provider_model_id      text NULL,

    usage_input_tokens     integer NULL,
    usage_output_tokens    integer NULL,

    stream_source_uri      text NULL,
    stream_source_node_id  text NULL,

    error_code             text NULL,
    error_detail           text NULL,

    kafka_topic            text NULL,
    kafka_partition        integer NULL,
    kafka_offset           bigint NULL,

    PRIMARY KEY (session_id, workflow_id)
);

CREATE INDEX IF NOT EXISTS idx_workflow_results_latest_tenant_created_at
    ON workflow_results_latest (tenant_id, created_at DESC);
