"""job_is_corrected

加 Job.is_corrected boolean 欄位，標「校正完成」、進 dataset 必要條件。
既有 rows 預設 0(False)、user 手動勾標。

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "is_corrected",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "is_corrected")
