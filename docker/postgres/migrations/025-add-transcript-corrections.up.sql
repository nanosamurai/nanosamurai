-- 025-add-transcript-corrections
--
-- Human corrections of final transcripts.
-- Keep every copy of this migration identical. Apply it in one transaction.
--
-- Rows are only appended. An edit is never updated or deleted; `undo` is a new
-- row that cancels one earlier edit. The machine output in
-- session_transcripts stays unchanged, and the corrected transcript is the
-- machine segments plus every edit that is not undone.
--
-- Kinds:
-- - segment_text:    new text of one machine segment     (new_value {text})
-- - segment_speaker: speaker of one machine segment      (new_value {speaker, speaker_id?})
-- - speaker_label:   speaker for every segment with a machine label
--                    (speaker_label, new_value {speaker, speaker_id?})
-- - undo:            cancels the edit in undoes_id
--
-- seq numbers the edits of one transcript from 1. The highest seq is the
-- version that clients send back for optimistic concurrency.

CREATE TABLE IF NOT EXISTS transcript_corrections (
    id              uuid PRIMARY KEY,
    tenant_id       uuid NOT NULL,
    session_id      uuid NOT NULL,
    transcript_id   uuid NOT NULL REFERENCES session_transcripts(id) ON DELETE CASCADE,
    seq             bigint NOT NULL,
    kind            text NOT NULL,
    segment_index   integer,
    speaker_label   text,
    old_value       jsonb NOT NULL DEFAULT '{}'::jsonb,
    new_value       jsonb NOT NULL DEFAULT '{}'::jsonb,
    undoes_id       uuid,
    audio_start_s   double precision,
    audio_end_s     double precision,
    author_user_id  uuid REFERENCES app_users(id) ON DELETE SET NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT transcript_corrections_session_fk
        FOREIGN KEY (session_id, tenant_id) REFERENCES sessions(id, tenant_id) ON DELETE CASCADE,
    CONSTRAINT transcript_corrections_transcript_seq_uniq UNIQUE (transcript_id, seq),
    CONSTRAINT transcript_corrections_id_transcript_uniq UNIQUE (id, transcript_id),
    CONSTRAINT transcript_corrections_undo_same_transcript_fk
        FOREIGN KEY (undoes_id, transcript_id)
        REFERENCES transcript_corrections(id, transcript_id) ON DELETE CASCADE,
    CONSTRAINT transcript_corrections_seq_check CHECK (seq > 0),
    CONSTRAINT transcript_corrections_kind_check CHECK (
        (kind IN ('segment_text', 'segment_speaker')
            AND segment_index >= 0 AND speaker_label IS NULL AND undoes_id IS NULL)
     OR (kind = 'speaker_label'
            AND segment_index IS NULL AND speaker_label IS NOT NULL AND undoes_id IS NULL)
     OR (kind = 'undo'
            AND segment_index IS NULL AND speaker_label IS NULL AND undoes_id IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS transcript_corrections_undo_once
    ON transcript_corrections (undoes_id) WHERE kind = 'undo';

CREATE INDEX IF NOT EXISTS idx_transcript_corrections_session
    ON transcript_corrections (tenant_id, session_id, transcript_id, seq);
