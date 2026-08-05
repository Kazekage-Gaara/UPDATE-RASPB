# Plan de Mejoras - SolinfNet Control Center

Documento vivo. Marcar con `[x]` cuando este hecho y anotar decisiones al final.

Ultima revision: 2026-07-30

---

## P0 - Arranque y Seguridad

- [x] **P0-1 Corregir rutas rotas de FastAPI**
  - Archivo: `backend/main.py`
  - Estado: corregidos los decoradores de `/api/configure/{ip}` y `/api/install_mono/{ip}`.
  - Verificacion: `python3 -m py_compile backend/main.py`.

- [x] **P0-2 Autenticacion por API Key**
  - Archivos: `backend/main.py`, `backend/index.html`, `.env.example`
  - Estado: la API valida `X-API-Key` cuando `API_KEY` esta definida; el frontend guarda la clave en `localStorage`, la envia en requests internas y reintenta tras 401.
  - Pendiente operativo: definir `API_KEY` en produccion.

- [x] **P0-3 Validar IPv4 antes de lanzar SSH/Celery**
  - Archivo: `backend/main.py`
  - Estado: `scan`, `update`, `configure`, `install_mono` e historial por IP normalizan y rechazan IPv4 invalidas.

- [x] **P0-4 Proteger endpoints de datos**
  - Archivo: `backend/main.py`
  - Estado: endpoints `/api/*` de inventario, reportes, historial, progreso y dossiers usan `verify_api_key`.

- [x] **P0-5 Evitar borrado accidental de estado/version**
  - Archivo: `backend/tasks.py`
  - Estado: `save_gateway_status(ip, None, None, ...)` ya no borra `version` ni `status` existentes.

- [ ] **P0-6 Rotar `RASP_PASSWORD`**
  - Riesgo: si alguna contraseña real estuvo en archivos o historial, debe considerarse comprometida.
  - Accion: rotar en gateways y mantenerla solo en `.env`.

- [ ] **P0-7 Migrar SSH a claves o mecanismo sin contraseña visible**
  - Archivos: `backend/ssh_utils.py`, `backend/tasks.py`
  - Riesgo: `sshpass -p` puede exponer la contraseña en procesos del contenedor.
  - Opciones: claves SSH por gateway, `SSH_ASKPASS`, o Paramiko con politica de hosts controlada.

---

## P1 - XSS, Robustez y Operacion

- [x] **P1-1 Reducir XSS en zonas nuevas del frontend**
  - Archivo: `backend/index.html`
  - Estado: `showToast`, acciones Configure/Mono y dossiers principales escapan datos dinamicos obvios.

- [ ] **P1-2 Cerrar XSS de forma sistematica**
  - Archivo: `backend/index.html`
  - Pendiente: revisar todos los usos restantes de `innerHTML`, `insertAdjacentHTML`, `onclick` dinamico y popups de mapas.
  - Mejor direccion: construir filas/modales con DOM APIs o helpers pequenos en vez de concatenar HTML.

- [x] **P1-3 Limite de tiempo para instalacion Mono**
  - Archivo: `backend/tasks.py`
  - Estado: `install_mono` usa `time_limit=10800`, `soft_time_limit=10740`, `acks_late=True`.

- [x] **P1-4 Indices para relaciones frecuentes**
  - Archivos: `backend/models.py`, `backend/database.py`
  - Estado: `cliente_id` y `unidad_id` tienen indices; `init_db()` crea indices faltantes en SQLite existente.

- [ ] **P1-5 Parametrizar credenciales `admin:admin`**
  - Archivo: `backend/tasks.py`
  - Accion: mover usuario/clave web del gateway a variables de entorno.

- [ ] **P1-6 Rate limiting en endpoints que disparan red**
  - Archivo: `backend/main.py`
  - Accion: limitar `/api/scan/{ip}`, `/api/update`, `/api/configure/{ip}`, `/api/install_mono/{ip}`.

- [ ] **P1-7 Control real de concurrencia**
  - Archivos: `backend/config.py`, `backend/tasks.py`, `docker-compose.yml`
  - Estado actual: existe `MAX_CONCURRENT_*`, pero no se aplica de forma centralizada.
  - Accion: separar colas Celery o usar semaforos/limits por tipo de tarea.

- [ ] **P1-8 Reemplazar `@app.on_event("startup")`**
  - Archivo: `backend/main.py`
  - Accion: migrar a `lifespan`.

- [ ] **P1-9 Servir HTML estatico eficientemente**
  - Archivo: `backend/main.py`
  - Accion: usar `FileResponse` o `StaticFiles` para no leer `index.html` a mano en cada request.

---

## P2 - Mantenimiento

- [ ] **P2-1 Tests unitarios minimos**
  - Sugerencia: `pytest` para `normalize_version`, validacion IPv4, parser de clientes, `save_gateway_status`.

- [ ] **P2-2 Migraciones con Alembic**
  - Motivo: los modelos evolucionan y SQLite existente necesita cambios repetibles.

- [ ] **P2-3 Limpiar archivos generados o pesados**
  - Candidatos: `backend/index.html.backup`, `__pycache__/`, `data/solinfnet.db` si no debe distribuirse.

- [ ] **P2-4 Scripts shell mas estrictos**
  - Archivos: `updates/*.sh`, `backend/scripts/install_mono.sh`
  - Accion: revisar `set -euo pipefail`, permisos, logs y comandos destructivos.

- [ ] **P2-5 Contenedor no-root**
  - Archivo: `backend/Dockerfile`
  - Accion: crear usuario de aplicacion y ajustar permisos de `/app/data`.

- [ ] **P2-6 Modularizar frontend**
  - Archivo: `backend/index.html`
  - Accion: separar JS en modulos (`api.js`, `inventory.js`, `reports.js`, `map.js`) cuando la seguridad basica este cerrada.

---

## Verificaciones actuales

- [x] `python3 -m py_compile backend/main.py backend/tasks.py backend/models.py backend/database.py backend/ssh_utils.py backend/parsers/parse_clientes.py`
- [ ] Prueba manual con `docker-compose up --build`
- [ ] Prueba manual de API key en navegador
- [ ] Prueba real contra gateway de scan/update/configure/mono

---

## Notas

- `.env` existe localmente y esta ignorado por `.gitignore`; no se debe abrir ni versionar.
- No hay repositorio git inicializado en este directorio, por lo que no se pudo revisar historial ni purgar secretos anteriores.
- Las mejoras de XSS aplicadas son una reduccion de riesgo, no una auditoria completa del frontend.
