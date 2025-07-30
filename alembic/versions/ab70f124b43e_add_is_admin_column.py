"""add_is_admin_column

Revision ID: ab70f124b43e
Revises: f3a4d8dcf585
Create Date: 2025-03-27 06:04:02.122684

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab70f124b43e'
down_revision: Union[str, None] = 'f3a4d8dcf585'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add is_admin column if it doesn't exist
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('is_admin', sa.Boolean(), server_default='0', nullable=False))

def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('is_admin')
