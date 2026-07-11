-- 003-sessions-started-at-nullable

ALTER TABLE sessions
  ALTER COLUMN started_at DROP NOT NULL;

ALTER TABLE sessions
  ALTER COLUMN started_at DROP DEFAULT;
