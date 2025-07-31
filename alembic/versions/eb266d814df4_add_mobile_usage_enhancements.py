"""add_mobile_usage_enhancements

Revision ID: eb266d814df4
Revises: c4a8511542e3
Create Date: 2025-07-31 12:01:40.064309

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eb266d814df4'
down_revision: Union[str, None] = 'c4a8511542e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns for enhanced mobile usage tracking
    with op.batch_alter_table('usage_limits') as batch_op:
        batch_op.add_column(sa.Column(
            'total_call_duration_this_week', sa.Integer(), nullable=True, default=0))
        batch_op.add_column(sa.Column(
            'total_call_duration_this_month', sa.Integer(), nullable=True, default=0))
        batch_op.add_column(sa.Column('addon_calls_remaining',
                            sa.Integer(), nullable=True, default=0))
        batch_op.add_column(sa.Column('addon_calls_expiry',
                            sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Remove new columns
    with op.batch_alter_table('usage_limits') as batch_op:
        batch_op.drop_column('addon_calls_expiry')
        batch_op.drop_column('addon_calls_remaining')
        batch_op.drop_column('total_call_duration_this_month')
        batch_op.drop_column('total_call_duration_this_week')
