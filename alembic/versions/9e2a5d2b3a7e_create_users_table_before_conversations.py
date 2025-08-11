from alembic import op
import sqlalchemy as sa

revision = "9e2a5d2b3a7e"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        # add real columns later if needed
    )

def downgrade():
    op.drop_table("users")
