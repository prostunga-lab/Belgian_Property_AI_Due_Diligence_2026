"""free trial of the subscription plans (once per organisation)

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('orgs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trial_used', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('orgs', schema=None) as batch_op:
        batch_op.drop_column('trial_ends_at')
        batch_op.drop_column('trial_used')
