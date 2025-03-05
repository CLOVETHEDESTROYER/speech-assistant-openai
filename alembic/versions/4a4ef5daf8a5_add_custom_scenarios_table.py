"""Add custom scenarios table

Revision ID: 4a4ef5daf8a5
Revises: 828dad0c27c1
Create Date: 2025-03-04 20:48:24.103469

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a4ef5daf8a5'
down_revision: Union[str, None] = '828dad0c27c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'custom_scenarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scenario_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('persona', sa.Text(), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('voice_type', sa.String(), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=True, default=0.7),
        sa.Column('created_at', sa.DateTime(),
                  nullable=True, default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scenario_id')
    )
    op.create_index(op.f('ix_custom_scenarios_scenario_id'),
                    'custom_scenarios', ['scenario_id'], unique=True)
    op.create_index(op.f('ix_custom_scenarios_id'),
                    'custom_scenarios', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_custom_scenarios_id'),
                  table_name='custom_scenarios')
    op.drop_index(op.f('ix_custom_scenarios_scenario_id'),
                  table_name='custom_scenarios')
    op.drop_table('custom_scenarios')
