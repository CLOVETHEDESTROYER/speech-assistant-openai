"""add_apple_signin_fields

Revision ID: f20c14b69504
Revises: f4dde98c9eae
Create Date: 2025-08-21 12:12:35.797227

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f20c14b69504'
down_revision: Union[str, None] = 'f4dde98c9eae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add Apple Sign In fields to users table
    op.add_column('users', sa.Column('apple_user_id', sa.String(), nullable=True))
    op.add_column('users', sa.Column('apple_email', sa.String(), nullable=True))
    op.add_column('users', sa.Column('apple_full_name', sa.String(), nullable=True))
    op.add_column('users', sa.Column('auth_provider', sa.String(), nullable=True, server_default='email'))
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=True, server_default='false'))
    
    # Make hashed_password nullable for Apple users
    op.alter_column('users', 'hashed_password', nullable=True)
    
    # Create indexes
    op.create_index(op.f('ix_users_apple_user_id'), 'users', ['apple_user_id'], unique=True)


def downgrade() -> None:
    # Remove indexes
    op.drop_index(op.f('ix_users_apple_user_id'), table_name='users')
    
    # Remove columns
    op.drop_column('users', 'apple_user_id')
    op.drop_column('users', 'apple_email')
    op.drop_column('users', 'apple_full_name')
    op.drop_column('users', 'auth_provider')
    op.drop_column('users', 'email_verified')
    
    # Make hashed_password required again
    op.alter_column('users', 'hashed_password', nullable=False)
