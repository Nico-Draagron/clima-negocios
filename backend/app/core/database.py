from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from typing import Generator
import logging
from contextlib import contextmanager

from .config import settings

logger = logging.getLogger(__name__)

# Configuração do engine
engine_config = {
    "pool_pre_ping": True,
    "echo": settings.ENVIRONMENT == "development",
}

if settings.ENVIRONMENT == "production":
    engine_config.update({
        "pool_size": 20,
        "max_overflow": 40,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    })
else:
    # Em desenvolvimento, usa NullPool para evitar problemas de conexão
    engine_config["poolclass"] = NullPool

engine = create_engine(settings.DATABASE_URL, **engine_config)

# SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
metadata = MetaData()
Base = declarative_base(metadata=metadata)

# Dependency para obter DB session
def get_db() -> Generator[Session, None, None]:
    """
    Dependency function que yields database session.
    Garante que a sessão é fechada após o uso.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager para usar em scripts e tarefas assíncronas.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# Health check do banco
def check_database_connection():
    """
    Verifica se a conexão com o banco está funcionando.
    """
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False

# Criar tabelas (apenas para desenvolvimento)
def init_db():
    """
    Cria todas as tabelas no banco de dados.
    Em produção, use migrations com Alembic.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        raise