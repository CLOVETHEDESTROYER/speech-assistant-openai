"""Merge multiple heads

Revision ID: b9e2b583b876
Revises: 0e73a4c793fe, a1b2c3d4e5f6
Create Date: 2025-06-08 09:53:19.233768

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9e2b583b876'
down_revision: Union[str, None] = ('0e73a4c793fe', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
