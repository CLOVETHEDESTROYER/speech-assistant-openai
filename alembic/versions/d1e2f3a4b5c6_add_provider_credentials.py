"""add provider credentials table

Revision ID: d1e2f3a4b5c6
Revises: b9e2b583b876
Create Date: 2025-08-08
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = '2fea136ed473'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'provider_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('openai_api_key', sa.String(), nullable=True),
        sa.Column('twilio_account_sid', sa.String(), nullable=True),
        sa.Column('twilio_auth_token', sa.String(), nullable=True),
        sa.Column('twilio_phone_number', sa.String(), nullable=True),
        sa.Column('twilio_vi_sid', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )


def downgrade():
    op.drop_table('provider_credentials')


