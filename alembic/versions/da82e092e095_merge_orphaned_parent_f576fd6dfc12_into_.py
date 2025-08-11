"""merge orphaned parent f576fd6dfc12 into main chain

Revision ID: da82e092e095
Revises: e001d39f6375, d1e2f3a4b5c6
Create Date: 2025-08-11 20:57:16.867999

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da82e092e095'
down_revision: Union[str, None] = ('e001d39f6375', 'd1e2f3a4b5c6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
