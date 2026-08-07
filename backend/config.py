import os

class Config:
    # ⭐️ IMPORTANTE: .strip() elimina espacios o saltos de línea ocultos del .env
    TARGET_VERSION = os.getenv("TARGET_VERSION", "6.5").strip()
    SSH_USER = os.getenv("SSH_USER", "solinfnet").strip()
    RASP_PASSWORD = os.getenv("RASP_PASSWORD", "")

    # C-2: API Key para autenticación de la API. Si está vacía, la auth queda deshabilitada
    # (modo dev). En producción debe estar definida (ver .env.example).
    # Generar con: openssl rand -hex 32
    API_KEY = os.getenv("API_KEY", "").strip()

    UPDATE_FILES = [
        "SolinfNet.exe",
        "limpar_logs.sh",
        "renomear.sh",
        "removekijonull.sh",
        "check_webpage.sh"
    ]

    UPDATES_DIR = "/app/updates"
    MAX_CONCURRENT_UPDATES = 5
    MAX_CONCURRENT_SCANS = 10
    SSH_TIMEOUT = 20
    PING_TIMEOUT = 2
    CURL_TIMEOUT = 5
    DB_BACKUP_DIR = os.getenv("DB_BACKUP_DIR", "data/backups").strip()
    DB_BACKUP_RETENTION_DAYS = int(os.getenv("DB_BACKUP_RETENTION_DAYS", "14"))
