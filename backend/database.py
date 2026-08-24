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
        # SQLite no aplica alteraciones de modelos existentes con create_all.
        # Estas columnas se agregan sin borrar el inventario ni los historicos.
        existing_gateway_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(gateways)")}
        for name, definition in {
            "maintenance_enabled": "BOOLEAN NOT NULL DEFAULT 0",
            "maintenance_reason": "VARCHAR",
        }.items():
            if name not in existing_gateway_columns:
                conn.exec_driver_sql(f"ALTER TABLE gateways ADD COLUMN {name} {definition}")

        existing_scan_run_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(scheduled_scan_runs)")}
        for name, definition in {
            "maintenance": "INTEGER NOT NULL DEFAULT 0",
            "new_issues": "INTEGER NOT NULL DEFAULT 0",
            "recovered": "INTEGER NOT NULL DEFAULT 0",
            "version_changes": "INTEGER NOT NULL DEFAULT 0",
            "relay_changes": "INTEGER NOT NULL DEFAULT 0",
            "alerts": "INTEGER NOT NULL DEFAULT 0",
            "source_run_id": "INTEGER",
        }.items():
            if name not in existing_scan_run_columns:
                conn.exec_driver_sql(f"ALTER TABLE scheduled_scan_runs ADD COLUMN {name} {definition}")

        existing_scan_result_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(scheduled_scan_gateway_results)")}
        for name, definition in {
            "version": "VARCHAR",
            "has_relay": "BOOLEAN",
            "previous_status": "VARCHAR",
            "change_types": "VARCHAR",
            "consecutive_failures": "INTEGER NOT NULL DEFAULT 0",
            "maintenance": "BOOLEAN NOT NULL DEFAULT 0",
        }.items():
            if name not in existing_scan_result_columns:
                conn.exec_driver_sql(f"ALTER TABLE scheduled_scan_gateway_results ADD COLUMN {name} {definition}")

        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_unidades_cliente_id ON unidades (cliente_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_gateways_cliente_id ON gateways (cliente_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_gateways_unidad_id ON gateways (unidad_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_scheduled_scan_results_gateway_finished ON scheduled_scan_gateway_results (gateway_ip, finished_at)")
