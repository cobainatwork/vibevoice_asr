"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-09

Creates all tables described in SPEC.md §7.2.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enums
JOB_STATUS = sa.Enum(
    "pending", "queued", "running", "done", "failed", "cancelled",
    name="jobstatus",
)
JOB_SOURCE = sa.Enum(
    "admin_upload", "v1_api_async", "v1_api_sync", "v1_api_ws",
    name="jobsource",
)
TRAINING_STATUS = sa.Enum(
    "pending", "preparing", "training", "merging", "done", "failed", "cancelled",
    name="trainingstatus",
)
MODEL_TYPE = sa.Enum("base", "merged", "lora", name="modeltype")
DATASET_SOURCE = sa.Enum(
    "uploaded", "from_transcription",
    "imported_xlsx", "imported_csv", "imported_srt",
    "imported_vtt", "imported_txt", "imported_json",
    name="datasetsource",
)
WEBHOOK_DELIVERY_STATUS = sa.Enum(
    "pending", "succeeded", "failed", "given_up",
    name="webhookdeliverystatus",
)


def upgrade() -> None:
    # === projects ===
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("hotwords", sa.JSON, nullable=False),
        sa.Column("active_model_id", sa.Integer),  # FK added below to break cycle
        sa.Column("webhook_url", sa.String(500)),
        sa.Column("webhook_secret", sa.String(64)),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # === model_versions === (referenced by projects via active_model_id)
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", MODEL_TYPE, nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("training_run_id", sa.String(36)),  # FK added below
        sa.Column("size_gb", sa.Float),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # Add cyclic FK now (use batch_alter_table for SQLite)
    with op.batch_alter_table("projects") as batch_op:
        batch_op.create_foreign_key(
            "fk_projects_active_model",
            "model_versions",
            ["active_model_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # === api_keys ===
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer,
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("key_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("key_prefix", sa.String(8), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_used_at", sa.DateTime),
        sa.Column("expires_at", sa.DateTime),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # === jobs ===
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("source", JOB_SOURCE, nullable=False),
        sa.Column("api_key_id", sa.Integer,
                  sa.ForeignKey("api_keys.id", ondelete="SET NULL")),
        sa.Column("idempotency_key", sa.String(100)),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("audio_path", sa.String(500), nullable=False),
        sa.Column("duration_sec", sa.Float),
        sa.Column("status", JOB_STATUS, nullable=False),
        sa.Column("progress", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("chunks_total", sa.Integer, nullable=False, server_default="1"),
        sa.Column("chunks_done", sa.Integer, nullable=False, server_default="0"),
        sa.Column("segments", sa.JSON),
        sa.Column("raw_text", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("used_hotwords", sa.JSON, nullable=False),
        sa.Column("used_model_id", sa.Integer,
                  sa.ForeignKey("model_versions.id", ondelete="SET NULL")),
        sa.Column("callback_url", sa.String(500)),
        sa.Column("metadata_extra", sa.JSON),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_job_idempotency"),
    )
    op.create_index("ix_jobs_idempotency_key", "jobs", ["idempotency_key"])

    # === integration_calls ===
    op.create_table(
        "integration_calls",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("api_key_id", sa.Integer,
                  sa.ForeignKey("api_keys.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("job_id", sa.String(36),
                  sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("endpoint", sa.String(100), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("source_ip", sa.String(45)),
        sa.Column("user_agent", sa.String(200)),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_integration_calls_created_at", "integration_calls", ["created_at"])

    # === webhook_deliveries ===
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.String(36),
                  sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", WEBHOOK_DELIVERY_STATUS, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime),
        sa.Column("last_response_code", sa.Integer),
        sa.Column("last_response_body", sa.Text),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("delivered_at", sa.DateTime),
    )
    op.create_index("ix_webhook_deliveries_next_attempt_at",
                    "webhook_deliveries", ["next_attempt_at"])

    # === dataset_items ===
    op.create_table(
        "dataset_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer,
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audio_path", sa.String(500), nullable=False),
        sa.Column("label", sa.JSON, nullable=False),
        sa.Column("duration_sec", sa.Float, nullable=False),
        sa.Column("source", DATASET_SOURCE, nullable=False),
        sa.Column("source_job_id", sa.String(36),
                  sa.ForeignKey("jobs.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    # === training_runs ===
    op.create_table(
        "training_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", TRAINING_STATUS, nullable=False),
        sa.Column("hyperparams", sa.JSON, nullable=False),
        sa.Column("dataset_item_ids", sa.JSON, nullable=False),
        sa.Column("output_path", sa.String(500)),
        sa.Column("merged_path", sa.String(500)),
        sa.Column("log_path", sa.String(500), nullable=False),
        sa.Column("metrics", sa.JSON),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("started_at", sa.DateTime),
        sa.Column("finished_at", sa.DateTime),
    )

    # Now wire model_versions.training_run_id → training_runs.id
    with op.batch_alter_table("model_versions") as batch_op:
        batch_op.create_foreign_key(
            "fk_model_versions_training_run",
            "training_runs",
            ["training_run_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    op.drop_table("training_runs")
    op.drop_table("dataset_items")
    op.drop_index("ix_webhook_deliveries_next_attempt_at", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_integration_calls_created_at", table_name="integration_calls")
    op.drop_table("integration_calls")
    op.drop_index("ix_jobs_idempotency_key", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("model_versions")
    op.drop_table("projects")
    JOB_STATUS.drop(op.get_bind(), checkfirst=True)
    JOB_SOURCE.drop(op.get_bind(), checkfirst=True)
    TRAINING_STATUS.drop(op.get_bind(), checkfirst=True)
    MODEL_TYPE.drop(op.get_bind(), checkfirst=True)
    DATASET_SOURCE.drop(op.get_bind(), checkfirst=True)
    WEBHOOK_DELIVERY_STATUS.drop(op.get_bind(), checkfirst=True)
