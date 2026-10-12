"""Append-only evidence guards and bounded policy constraints."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

EVIDENCE_TABLES = (
    "source_policies",
    "artifacts",
    "fetch_receipts",
    "publication_occurrences",
    "article_revisions",
    "feed_item_observations",
    "availability_witnesses",
    "consumptions",
    "source_health_intervals",
    "snapshots",
    "snapshot_invalidations",
    "audit_events",
)


def upgrade():
    op.create_foreign_key(
        "fk_source_policy_head", "sources", "source_policies", ["current_policy_id"], ["id"]
    )
    op.create_check_constraint(
        "policy_retention_positive",
        "source_policies",
        "retention_seconds > 0 AND expires_at > effective_from",
    )
    op.create_check_constraint(
        "policy_limits_bounded",
        "source_policies",
        "max_bytes BETWEEN 1 AND 4194304 AND max_items BETWEEN 0 AND 1000 "
        "AND max_depth BETWEEN 1 AND 64 AND timeout_seconds BETWEEN 1 AND 30",
    )
    op.create_check_constraint("attempt_fence_nonnegative", "fetch_attempts", "fence >= 0")
    op.create_index("ix_attempt_due", "fetch_attempts", ["state", "due_at"])
    op.create_index("ix_outbox_due", "outbox", ["topic", "state", "due_at"])
    op.create_index(
        "ix_observation_occurrence", "feed_item_observations", ["occurrence_id", "received_at"]
    )
    op.create_index("ix_health_source", "source_health_intervals", ["source_id", "recorded_at"])
    op.execute("""
        CREATE FUNCTION pulse_evidence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' AND TG_TABLE_NAME IN ('article_revisions', 'feed_item_observations')
             AND current_setting('pulse.allow_erasure', true) = 'on' THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION 'append-only evidence: % % forbidden', TG_TABLE_NAME, TG_OP;
        END $$
    """)
    for table in EVIDENCE_TABLES:
        op.execute(
            f"CREATE TRIGGER evidence_guard BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION pulse_evidence_guard()"
        )


def downgrade():
    for table in EVIDENCE_TABLES:
        op.execute(f"DROP TRIGGER evidence_guard ON {table}")
    op.execute("DROP FUNCTION pulse_evidence_guard()")
    op.drop_index("ix_health_source", table_name="source_health_intervals")
    op.drop_index("ix_observation_occurrence", table_name="feed_item_observations")
    op.drop_index("ix_outbox_due", table_name="outbox")
    op.drop_index("ix_attempt_due", table_name="fetch_attempts")
    op.drop_constraint("attempt_fence_nonnegative", "fetch_attempts")
    op.drop_constraint("policy_limits_bounded", "source_policies")
    op.drop_constraint("policy_retention_positive", "source_policies")
    op.drop_constraint("fk_source_policy_head", "sources")
