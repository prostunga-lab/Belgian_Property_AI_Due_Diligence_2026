"""access requests (public contact form) and account type (individual / professional)

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('access_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=False),
    sa.Column('account_type', sa.String(length=12), nullable=False),
    sa.Column('organisation', sa.String(length=200), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('lang', sa.String(length=5), nullable=False),
    sa.Column('status', sa.String(length=12), server_default='new', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('access_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_access_requests_email'), ['email'], unique=False)
    with op.batch_alter_table('orgs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('account_type', sa.String(length=12), server_default='professional', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('orgs', schema=None) as batch_op:
        batch_op.drop_column('account_type')
    with op.batch_alter_table('access_requests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_access_requests_email'))
    op.drop_table('access_requests')
