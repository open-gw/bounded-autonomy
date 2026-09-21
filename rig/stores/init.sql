-- Rig workload schema. Temporal-table pattern on `records`.
CREATE TABLE IF NOT EXISTS records (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    task_id TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS records_history (
    id BIGSERIAL PRIMARY KEY,
    key TEXT NOT NULL,
    before JSONB,
    after JSONB,
    op TEXT NOT NULL,
    task_id TEXT,
    at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION records_history_trigger() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO records_history(key, before, after, op, task_id)
        VALUES (OLD.key, to_jsonb(OLD), NULL, 'DELETE', current_setting('rig.task_id', true));
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO records_history(key, before, after, op, task_id)
        VALUES (NEW.key, to_jsonb(OLD), to_jsonb(NEW), 'UPDATE', current_setting('rig.task_id', true));
        RETURN NEW;
    ELSE
        INSERT INTO records_history(key, before, after, op, task_id)
        VALUES (NEW.key, NULL, to_jsonb(NEW), 'INSERT', current_setting('rig.task_id', true));
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS records_history_trg ON records;
CREATE TRIGGER records_history_trg
    AFTER INSERT OR UPDATE OR DELETE ON records
    FOR EACH ROW EXECUTE FUNCTION records_history_trigger();

-- Logical decoding for the ground-truth subscriber.
ALTER SYSTEM SET wal_level = logical;
SELECT pg_create_logical_replication_slot('rig_gt', 'test_decoding')
WHERE NOT EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = 'rig_gt');
