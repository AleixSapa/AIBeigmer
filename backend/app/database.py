from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

# Production uses PostgreSQL/Supabase. SQLite is intentionally not used.
database_url = settings.database_url
if not database_url or database_url.startswith('sqlite'):
    raise RuntimeError('DATABASE_URL must point to PostgreSQL/Supabase; SQLite is not supported.')

engine = create_engine(database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
