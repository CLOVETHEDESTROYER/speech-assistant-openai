"""add_transcript_sid_to_conversations

Revision ID: f3a4d8dcf585
Revises: 4a4ef5daf8a5
Create Date: 2025-03-25 13:33:38.794055

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a4d8dcf585'
down_revision: Union[str, None] = '4a4ef5daf8a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add transcript_sid column to conversations table
    op.add_column('conversations', sa.Column(
        'transcript_sid', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove transcript_sid column from conversations table
    op.drop_column('conversations', 'transcript_sid')
