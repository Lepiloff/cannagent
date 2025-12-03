
from alembic import op
import sqlalchemy as sa
import os
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = '1d89c2f83dc2'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension exists before adding vector columns
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Add energy_type to feelings
    op.add_column('strains_feeling', sa.Column('energy_type', sa.String(length=20), nullable=True))

    # Add multilingual embeddings to strains
    dimension = int(os.getenv('VECTOR_DIMENSION', '1536'))
    op.add_column('strains_strain', sa.Column('embedding_en', Vector(dimension), nullable=True))
    op.add_column('strains_strain', sa.Column('embedding_es', Vector(dimension), nullable=True))


def downgrade() -> None:
    op.drop_column('strains_strain', 'embedding_es')
    op.drop_column('strains_strain', 'embedding_en')
    op.drop_column('strains_feeling', 'energy_type')
