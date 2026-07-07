-- Vendored from samuraipersistor/resources/migrations/003-webhook-delivery-outcomes.up.sql
--
-- Persist webhook dispatcher attempt outcomes for audit/UI.
--
-- Notes:
-- - Append-only history table: webhook_delivery_outcomes
-- - Fast list view table: webhook_delivery_latest (last status per webhook)
-- - No FK to sessions: this is an audit lane and must not block on missing rows.

CREATE TABLE webhook_delivery_outcomes (
    id              uuid PRIMARY KEY,
    created_at      timestamptz NOT NULL,
    tenant_id       uuid NOT NULL,
    session_id      uuid NULL,
    webhook_id      text NOT NULL,
    dispatch_id     uuid NOT NULL,
    event_id        text NULL,
    event_type      text NOT NULL,
    attempt_no      integer NOT NULL,
    status          text NOT NULL,
    http_status     integer NULL,
    error_code      text NULL,
    error_detail    text NULL,
    latency_ms      bigint NULL,
    kafka_topic     text NULL,
    kafka_partition integer NULL,
    kafka_offset    bigint NULL
);

-- Idempotency under Kafka redeliveries.
ALTER TABLE webhook_delivery_outcomes
    ADD CONSTRAINT webhook_delivery_outcomes_dispatch_attempt_uniq
    UNIQUE (dispatch_id, attempt_no);

CREATE INDEX idx_webhook_delivery_outcomes_tenant_created_at
    ON webhook_delivery_outcomes (tenant_id, created_at DESC);

CREATE INDEX idx_webhook_delivery_outcomes_webhook_created_at
    ON webhook_delivery_outcomes (webhook_id, created_at DESC);

CREATE INDEX idx_webhook_delivery_outcomes_session_created_at
    ON webhook_delivery_outcomes (session_id, created_at DESC);

CREATE INDEX idx_webhook_delivery_outcomes_dispatch
    ON webhook_delivery_outcomes (dispatch_id);


CREATE TABLE webhook_delivery_latest (
    tenant_id         uuid NOT NULL,
    webhook_id        text NOT NULL,
    last_created_at   timestamptz NOT NULL,
    last_status       text NOT NULL,
    last_http_status  integer NULL,
    last_error_code   text NULL,
    last_error_detail text NULL,
    last_latency_ms   bigint NULL,
    last_event_type   text NULL,
    last_dispatch_id  uuid NULL,
    last_attempt_no   integer NULL,
    PRIMARY KEY (tenant_id, webhook_id)
);

CREATE INDEX idx_webhook_delivery_latest_tenant_last_created_at
    ON webhook_delivery_latest (tenant_id, last_created_at DESC);
