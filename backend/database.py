from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Crear carpeta data si no existe
os.makedirs("data", exist_ok=True)

# Configuración SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/solinfnet.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency para obtener sesión de BD"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Crear tablas al iniciar"""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_unidades_cliente_id ON unidades (cliente_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_gateways_cliente_id ON gateways (cliente_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_gateways_unidad_id ON gateways (unidad_id)")
