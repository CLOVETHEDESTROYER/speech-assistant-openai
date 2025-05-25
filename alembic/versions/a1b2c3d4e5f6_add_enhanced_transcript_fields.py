"""add_enhanced_transcript_fields

Revision ID: a1b2c3d4e5f6
Revises: f3a4d8dcf585
Create Date: 2025-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f3a4d8dcf585'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add enhanced fields to transcript_records table
    op.add_column('transcript_records', sa.Column(
        'call_date', sa.DateTime(), nullable=True))
    op.add_column('transcript_records', sa.Column(
        'participant_info', sa.JSON(), nullable=True))
    op.add_column('transcript_records', sa.Column(
        'conversation_flow', sa.JSON(), nullable=True))
    op.add_column('transcript_records', sa.Column(
        'media_url', sa.String(), nullable=True))
    op.add_column('transcript_records', sa.Column(
        'source_type', sa.String(), nullable=True))
    op.add_column('transcript_records', sa.Column(
        'call_direction', sa.String(), nullable=True))
    op.add_column('transcript_records', sa.Column(
        'scenario_name', sa.String(), nullable=True))
    op.add_column('transcript_records', sa.Column(
        'summary_data', sa.JSON(), nullable=True))


def downgrade() -> None:
    # Remove enhanced fields from transcript_records table
    op.drop_column('transcript_records', 'summary_data')
    op.drop_column('transcript_records', 'scenario_name')
    op.drop_column('transcript_records', 'call_direction')
    op.drop_column('transcript_records', 'source_type')
    op.drop_column('transcript_records', 'media_url')
    op.drop_column('transcript_records', 'conversation_flow')
    op.drop_column('transcript_records', 'participant_info')
    op.drop_column('transcript_records', 'call_date')
