"""merge subscription_status and is_admin columns

Revision ID: 3e22308a5d75
Revises: 949f6ba259b3, ab70f124b43e
Create Date: 2025-06-30 05:08:18.272068

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e22308a5d75'
down_revision: Union[str, None] = ('949f6ba259b3', 'ab70f124b43e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
