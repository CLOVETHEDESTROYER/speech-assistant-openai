"""add conversations table

Revision ID: 2b49f111bb5f
Revises: 2024_02_25_add_conversations
Create Date: 2025-02-25 17:15:26.114177

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2b49f111bb5f'
down_revision: Union[str, None] = '2024_02_25_add_conversations'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
