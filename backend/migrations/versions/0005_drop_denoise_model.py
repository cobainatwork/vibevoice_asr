"""drop_denoise_model

換成 noisereduce 後不再分 model、denoise_model 欄位是 dead data,
查 DB 還看到 zipenhancer / gtcrn 值會誤導,直接 drop。

SQLite < 3.35 用 batch_alter_table 模式(內部 CREATE TABLE / COPY / DROP / RENAME)。

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("denoise_model")


def downgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "denoise_model",
            sa.String(20),
            server_default=sa.text("'gtcrn'"),
            nullable=False,
        ),
    )
