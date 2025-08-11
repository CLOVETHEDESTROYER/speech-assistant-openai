"""create users table (pre-conversations)

Revision ID: a9f0357750b6
Revises: da82e092e095
Create Date: 2025-08-11 21:01:27.491828

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9f0357750b6'
down_revision: Union[str, None] = 'da82e092e095'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
