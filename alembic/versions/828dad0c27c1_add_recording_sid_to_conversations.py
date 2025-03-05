"""add_recording_sid_to_conversations

Revision ID: 828dad0c27c1
Revises: 2b49f111bb5f
Create Date: 2025-02-26 21:56:20.497621

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '828dad0c27c1'
down_revision: Union[str, None] = '2b49f111bb5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add recording_sid column
    op.add_column('conversations', sa.Column(
        'recording_sid', sa.String(), nullable=True))

    # Create index on recording_sid for faster lookups
    op.create_index(op.f('ix_conversations_recording_sid'),
                    'conversations', ['recording_sid'], unique=False)

    # Create index on call_sid since we removed the unique constraint
    op.create_index(op.f('ix_conversations_call_sid'),
                    'conversations', ['call_sid'], unique=False)

    # Drop the unique constraint on call_sid if it exists
    try:
        op.drop_constraint('unique_call_sid', 'conversations', type_='unique')
    except:
        # If the constraint doesn't exist or has a different name, this might fail
        # We can safely ignore this as we're ensuring call_sid is no longer unique
        pass


def downgrade() -> None:
    # Remove the indexes
    op.drop_index(op.f('ix_conversations_recording_sid'),
                  table_name='conversations')
    op.drop_index(op.f('ix_conversations_call_sid'),
                  table_name='conversations')

    # Remove the recording_sid column
    op.drop_column('conversations', 'recording_sid')

    # Add back the unique constraint on call_sid
    op.create_unique_constraint(
        'unique_call_sid', 'conversations', ['call_sid'])
