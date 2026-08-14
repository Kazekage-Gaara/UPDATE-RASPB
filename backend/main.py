from fastapi import FastAPI, Request, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, case, desc
from tasks import scan_and_check_version, update_gateway
from database import get_db, init_db
from models import Gateway, UpdateHistory, GatewayDiagnosticEvent, Cliente, Unidad
from config import Config
from datetime import datetime
from zoneinfo import ZoneInfo
import os, io, xlsxwriter, secrets, ipaddress, threading, time, sqlite3, re

app = FastAPI(title="SolinfNet Control Center")
templates = Jinja2Templates(directory=".")
update_tasks = {}
APP_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def app_now() -> datetime:
    """Hora de referencia del panel, compatible con las columnas SQLite actuales."""
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def serialize_datetime(value: datetime | None) -> str | None:
    """Envía fechas con zona explícita, también para registros SQLite históricos."""
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=APP_TIMEZONE)
    return value.astimezone(APP_TIMEZONE).isoformat()


def mono_incident_is_resolved(event: GatewayDiagnosticEvent, resolved_events: list[GatewayDiagnosticEvent]) -> tuple[bool, datetime | None]:
    """Determina si una alerta Mono ya fue corregida, tambien para datos anteriores."""
    explicit_resolution = next(
        (item for item in resolved_events if item.gateway_ip == event.gateway_ip and item.timestamp >= event.timestamp),
        None,
    )
    if explicit_resolution:
        return True, explicit_resolution.timestamp

    # Antes de registrar eventos de resolucion, el resultado de la limpieza ya
    # incluia el espacio libre final; sirve para clasificar el historial legado.
    match = re.search(r"espacio libre despues:\s*(\d+)\s*MB", event.details or "", re.IGNORECASE)
    if match and int(match.group(1)) > 100:
        return True, event.timestamp
    return False, None


def get_mono_incidents(db: Session, cliente_id: int | None = None) -> list[dict]:
    """Obtiene incidentes de espacio, conservando el estado y fecha de resolucion."""
    events_query = db.query(GatewayDiagnosticEvent).filter(
        GatewayDiagnosticEvent.event_type.in_(["MONO_NO_SPACE", "MONO_SPACE_RESOLVED"])
    )
    events = events_query.order_by(GatewayDiagnosticEvent.timestamp.desc()).all()
    detections = [event for event in events if event.event_type == "MONO_NO_SPACE"]
    resolutions = [event for event in events if event.event_type == "MONO_SPACE_RESOLVED"]

    gateways = db.query(Gateway).filter(Gateway.ip.in_({event.gateway_ip for event in detections})).all() if detections else []
    gateways_by_ip = {gateway.ip: gateway for gateway in gateways}
    if cliente_id is not None:
        detections = [event for event in detections if gateways_by_ip.get(event.gateway_ip) and gateways_by_ip[event.gateway_ip].cliente_id == cliente_id]

    incidents = []
    for event in detections:
        resolved, resolved_at = mono_incident_is_resolved(event, resolutions)
        incidents.append({
            "ip": event.gateway_ip,
            "detected_at": serialize_datetime(event.timestamp),
            "resolved": resolved,
            "resolved_at": serialize_datetime(resolved_at),
            "details": event.details,
            "gateway": gateways_by_ip.get(event.gateway_ip),
        })
    return incidents

# ============ C-2: AUTENTICACIÓN POR API KEY ============
# Header esperado: X-API-Key: <clave>
# Si Config.API_KEY está vacía → auth deshabilitada (modo dev).
# Si está definida → comparación constant-time contra el header.
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(_api_key_header)) -> bool:
    """Dependencia FastAPI. Si Config.API_KEY está vacía, no exige clave (dev).
    Si está definida, requiere X-API-Key y compara en tiempo constante."""
    if not Config.API_KEY:
        # Modo desarrollo: loggear una vez para que el operador sepa que la auth está off.
        return True
    if not api_key or not secrets.compare_digest(api_key, Config.API_KEY):
        raise HTTPException(
            status_code=401,
            detail="API Key inválida o ausente. Enviar header 'X-API-Key: <clave>'.",
        )
    return True
# ======================================================

def validate_ipv4(ip: str) -> str:
    """Normaliza y valida IPs antes de lanzar operaciones de red."""
    try:
        return str(ipaddress.IPv4Address(ip))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"IPv4 inválida: {ip}")


@app.get("/api/time")
async def get_server_time(_auth: bool = Depends(verify_api_key)):
    """Referencia NTP del servidor para relojes iguales en todos los navegadores."""
    return {"now": serialize_datetime(app_now()), "timezone": "America/Sao_Paulo"}

_client_import_scheduler_started = False
_database_backup_scheduler_started = False

def import_clients_from_presets():
    try:
        from parsers.parse_clientes import importar_todos_los_clientes
        total = importar_todos_los_clientes(limpiar_previo=False)
        print(f"[CLIENTES] Importacion de presets completada: {total} clientes procesados")
    except Exception as e:
        print(f"[CLIENTES] Error importando presets: {e}")

def start_client_import_scheduler():
    global _client_import_scheduler_started
    if _client_import_scheduler_started:
        return
    _client_import_scheduler_started = True

    def loop():
        while True:
            time.sleep(24 * 60 * 60)
            import_clients_from_presets()

    threading.Thread(target=loop, daemon=True, name="client-preset-importer").start()


def cleanup_old_database_backups():
    retention_days = max(int(Config.DB_BACKUP_RETENTION_DAYS), 1)
    cutoff = time.time() - (retention_days * 24 * 60 * 60)
    try:
        for name in os.listdir(Config.DB_BACKUP_DIR):
            if not (name.startswith("solinfnet-") and name.endswith(".db")):
                continue
            path = os.path.join(Config.DB_BACKUP_DIR, name)
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                print(f"[BACKUP] Backup antiguo eliminado: {path}")
    except FileNotFoundError:
        return
    except Exception as e:
        print(f"[BACKUP] Error limpiando backups antiguos: {e}")

def backup_database_if_needed(force: bool = False):
    source = os.path.abspath("data/solinfnet.db")
    if not os.path.exists(source):
        print(f"[BACKUP] BD no encontrada, se omite backup: {source}")
        return None

    os.makedirs(Config.DB_BACKUP_DIR, exist_ok=True)
    today = app_now().strftime("%Y%m%d")
    if not force:
        existing_today = [
            name for name in os.listdir(Config.DB_BACKUP_DIR)
            if name.startswith(f"solinfnet-{today}-") and name.endswith(".db")
        ]
        if existing_today:
            cleanup_old_database_backups()
            return os.path.join(Config.DB_BACKUP_DIR, sorted(existing_today)[-1])

    stamp = app_now().strftime("%Y%m%d-%H%M%S")
    target = os.path.join(Config.DB_BACKUP_DIR, f"solinfnet-{stamp}.db")
    try:
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
        cleanup_old_database_backups()
        print(f"[BACKUP] Backup de BD creado: {target}")
        return target
    except Exception as e:
        print(f"[BACKUP] Error creando backup de BD: {e}")
        try:
            if os.path.exists(target):
                os.remove(target)
        except Exception:
            pass
        return None

def start_database_backup_scheduler():
    global _database_backup_scheduler_started
    if _database_backup_scheduler_started:
        return
    _database_backup_scheduler_started = True

    def loop():
        backup_database_if_needed()
        while True:
            time.sleep(24 * 60 * 60)
            backup_database_if_needed()

    threading.Thread(target=loop, daemon=True, name="database-backup-scheduler").start()

@app.on_event("startup")
def startup():
    init_db()
    import_clients_from_presets()
    start_client_import_scheduler()
    start_database_backup_scheduler()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # Servimos el HTML sin Jinja2: el archivo no usa variables de plantilla,
    # y así evitamos que {{ }} / {% %} del JavaScript rompan el render (500).
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/logo.png")
async def get_logo():
    p = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(p): return FileResponse(p, media_type="image/png")
    raise HTTPException(status_code=404, detail="Logo no encontrado")

@app.get("/favicon.ico")
async def get_favicon():
    p = os.path.join(os.path.dirname(__file__), "favicon.ico")
    if os.path.exists(p):
        # El archivo actual es un PNG 32x32 aunque el nombre sea .ico.
        return FileResponse(p, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
    # Fallback: si borraste favicon.ico, devolvemos el logo
    p = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(p):
        return FileResponse(p, media_type="image/x-icon", headers={"Cache-Control": "public, max-age=86400"})
    raise HTTPException(status_code=404, detail="Favicon no encontrado")

@app.post("/api/scan/{ip}")
async def scan_ip(ip: str, discovery: bool = False, _auth: bool = Depends(verify_api_key)):
    # En descubrimiento, los candidatos que no sean gateways válidos no se guardan.
    ip = validate_ipv4(ip)
    t = scan_and_check_version.delay(ip, not discovery)
    return {"task_id": t.id, "ip": ip, "discovery": discovery}

@app.get("/api/status/{task_id}")
async def get_status(task_id: str, _auth: bool = Depends(verify_api_key)):
    t = scan_and_check_version.AsyncResult(task_id)
    if t.state == 'PENDING': return {"state": t.state, "status": "Procesando..."}
    elif t.state != 'FAILURE': return {"state": t.state, "result": t.result}
    else: return {"state": t.state, "error": str(t.info)}

@app.get("/api/gateways")
async def get_gateways(db: Session = Depends(get_db), _auth: bool = Depends(verify_api_key)):
    gateways = db.query(Gateway, Cliente, Unidad).outerjoin(
        Cliente, Gateway.cliente_id == Cliente.id
    ).outerjoin(
        Unidad, Gateway.unidad_id == Unidad.id
    ).order_by(Gateway.last_scan.desc()).all()
    
    return [{
        "id": g.id, 
        "ip": g.ip, 
        "version": g.version, 
        "status": g.status, 
        "last_scan": serialize_datetime(g.last_scan),
        "last_update": serialize_datetime(g.last_update),
        "cliente": c.nombre if c else None,
        "cliente_id": c.id if c else None,
        "unidad": u.nombre if u else None,
        "unidad_id": u.id if u else None,
        "cultivo": c.tipo_cultivo if c else None,
        "description": g.description,
        "fleet_number": g.fleet_number,
        "latitude": g.latitude,
        "longitude": g.longitude,
        "vid": g.vid,
        "hardware_type": g.hardware_type,
        "use_gps": g.use_gps,
        "has_relay": g.has_relay,  # 🆕 NUEVO
        "os_version": g.os_version,
        "os_codename": g.os_codename
    } for g, c, u in gateways]

@app.get("/api/gateway/{ip}/history")
async def get_gateway_history(ip: str, db: Session = Depends(get_db), _auth: bool = Depends(verify_api_key)):
    ip = validate_ipv4(ip)
    h = db.query(UpdateHistory).filter(UpdateHistory.gateway_ip == ip).order_by(UpdateHistory.timestamp.desc()).all()
    return [{"id": x.id, "old_version": x.old_version, "new_version": x.new_version, "status": x.status,
             "duration_seconds": x.duration_seconds, "error_message": x.error_message,
             "timestamp": serialize_datetime(x.timestamp)} for x in h]

@app.post("/api/update")
async def start_update(request: Request, db: Session = Depends(get_db), _auth: bool = Depends(verify_api_key)):
    # C-2: requiere X-API-Key
    body = await request.json(); ips = body.get("ips", [])
    force = bool(body.get("force", False))
    if not ips: raise HTTPException(400, "No se proporcionaron IPs")
    if len(ips) > 5: raise HTTPException(400, "Máximo 5 actualizaciones simultáneas")
    ips = [validate_ipv4(ip) for ip in ips]
    out = []
    for ip in ips:
        t = update_gateway.delay(ip, force); out.append({"ip": ip, "task_id": t.id})
        update_tasks[t.id] = {"ip": ip, "started_at": app_now(), "force": force}
    action = "reinstalación" if force else "actualización"
    return {"message": f"Iniciando {action} de {len(ips)} gateways", "tasks": out, "force": force}

@app.get("/api/update/status/{task_id}")
async def get_update_status(task_id: str, _auth: bool = Depends(verify_api_key)):
    t = update_gateway.AsyncResult(task_id)
    info = update_tasks.get(task_id)
    result_ip = t.result.get("ip") if t.state == 'SUCCESS' and isinstance(t.result, dict) else None
    ip = info["ip"] if info else result_ip

    if not ip and t.state not in ('SUCCESS', 'FAILURE'):
        raise HTTPException(404, "Tarea no encontrada")
    if t.state == 'PENDING': return {"state": t.state, "ip": ip, "step": 0, "message": "En cola...", "percent": 0}
    elif t.state == 'PROGRESS': return {"state": t.state, "ip": ip, "step": t.info.get('step',0), "message": t.info.get('message',''), "percent": t.info.get('percent',0)}
    elif t.state == 'SUCCESS': return {"state": t.state, "ip": ip, "result": t.result, "step": 13, "percent": 100}
    elif t.state == 'FAILURE': return {"state": t.state, "ip": ip, "error": str(t.info), "step": 0, "percent": 0}
    else: return {"state": t.state, "ip": ip, "step": 0, "message": t.state, "percent": 0}

@app.get("/api/update/progress")
async def get_update_progress(_auth: bool = Depends(verify_api_key)):
    """Estado de actualizaciones: limpia terminadas y detecta PENDING zombie / worker ocupado."""
    act, comp = [], []
    finished_ids = []
    now = app_now()

    for tid, info in list(update_tasks.items()):
        t = update_gateway.AsyncResult(tid)
        ip = info["ip"]
        started = info.get("started_at")
        edad = (now - started).total_seconds() if started else 0

        if t.state in ('SUCCESS', 'FAILURE'):
            # Terminada → a completadas y la sacamos del dict
            finished_ids.append(tid)
            comp.append({"ip": ip, "task_id": tid, "state": t.state,
                         "result": t.result if t.state == 'SUCCESS' else {"ip": ip, "status": "FAILED", "msg": str(t.info)}})

        elif t.state == 'PENDING':
            if edad > 600:  # 10 min en cola sin que el worker la tome = zombie
                finished_ids.append(tid)
                comp.append({"ip": ip, "task_id": tid, "state": "FAILURE",
                             "result": {"ip": ip, "status": "FAILED",
                                        "msg": "⚠️ El worker no tomó la tarea (¿está caído o con los 5 slots ocupados? Revisá `docker compose logs worker`)."}})
            else:
                # En cola real: worker ocupado o arrancando → mensaje claro, no "PENDING" seco
                act.append({"ip": ip, "task_id": tid, "state": "PENDING", "percent": 0,
                            "message": "⏳ En cola (worker ocupado o reiniciando)..." if edad > 20 else "En cola..."})

        else:  # STARTED / PROGRESS
            act.append({"ip": ip, "task_id": tid, "state": t.state,
                        "percent": t.info.get('percent', 0) if t.state == 'PROGRESS' else 0,
                        "message": t.info.get('message', 'Procesando...') if t.state == 'PROGRESS' else t.state})

    for tid in finished_ids:           # 🔑 evita acumulación infinita
        update_tasks.pop(tid, None)

    return {"active": act, "completed": comp, "total": len(update_tasks)}

@app.get("/api/reportes/gateways_estado/{status_group}")
async def get_gateways_by_report_status(status_group: str, cultivo: str | None = None, db: Session = Depends(get_db), _auth: bool = Depends(verify_api_key)):
    """Lista gateways por estado operativo para drill-down desde los graficos."""
    status_map = {
        "PENDING": ["PENDING"],
        "OFFLINE": ["OFFLINE", "ERROR"],
        "FROZEN_CARD": ["FROZEN_CARD"],
    }
    statuses = status_map.get(status_group.upper())
    if not statuses:
        raise HTTPException(status_code=400, detail="Estado de reporte invalido")

    rows_query = db.query(Gateway, Cliente, Unidad).outerjoin(
        Cliente, Gateway.cliente_id == Cliente.id
    ).outerjoin(
        Unidad, Gateway.unidad_id == Unidad.id
    ).filter(Gateway.status.in_(statuses))

    if cultivo:
        if cultivo == "Sin Asignar":
            rows_query = rows_query.filter(Cliente.tipo_cultivo == None)
        else:
            rows_query = rows_query.filter(Cliente.tipo_cultivo == cultivo)

    rows = rows_query.order_by(Cliente.nombre.asc(), Unidad.nombre.asc(), Gateway.ip.asc()).all()
    return {
        "status_group": status_group.upper(),
        "cultivo": cultivo,
        "total": len(rows),
        "gateways": [{
            "id": g.id,
            "ip": g.ip,
            "version": g.version,
            "status": g.status,
            "last_scan": serialize_datetime(g.last_scan),
            "last_update": serialize_datetime(g.last_update),
            "cliente": c.nombre if c else None,
            "cliente_id": c.id if c else None,
            "unidad": u.nombre if u else None,
            "unidad_id": u.id if u else None,
            "cultivo": c.tipo_cultivo if c else None,
            "description": g.description,
            "fleet_number": g.fleet_number,
            "has_relay": g.has_relay,
            "os_version": g.os_version,
        } for g, c, u in rows]
    }

@app.get("/api/reportes/dashboard")
async def get_dashboard_data(db: Session = Depends(get_db), _auth: bool = Depends(verify_api_key)):
    """Obtiene las estadísticas para los gráficos del dashboard"""
    try:
        # 1. Totales globales
        total = db.query(Gateway).count()
        act = db.query(Gateway).filter(Gateway.status == 'UPDATED').count()
        pend = db.query(Gateway).filter(Gateway.status == 'PENDING').count()
        off = db.query(Gateway).filter(Gateway.status.in_(['OFFLINE', 'ERROR'])).count()
        frozen = db.query(Gateway).filter(Gateway.status == 'FROZEN_CARD').count()
        
        # 🆕 NUEVO: Estadísticas de Relay LPWAN
        con_relay = db.query(Gateway).filter(Gateway.has_relay == True).count()
        sin_relay = db.query(Gateway).filter(Gateway.has_relay == False).count()
        relay_null = db.query(Gateway).filter(Gateway.has_relay == None).count()

        mono_incidents = get_mono_incidents(db)
        active_mono_ips = {item["ip"] for item in mono_incidents if not item["resolved"]}
        frozen_event_ips = {ip for (ip,) in db.query(GatewayDiagnosticEvent.gateway_ip)\
            .filter(GatewayDiagnosticEvent.event_type == "FROZEN_CARD")\
            .distinct()\
            .all() if ip}
        current_frozen_ips = {ip for (ip,) in db.query(Gateway.ip).filter(Gateway.status == "FROZEN_CARD").all()}
        frozen_ips = frozen_event_ips | current_frozen_ips
        diagnostic_counts = {
            "MONO_NO_SPACE": len(active_mono_ips - frozen_ips),
            "FROZEN_CARD": len(frozen_ips),
        }

        # 2. Estadísticas por Tipo de Cultivo
        stats = db.query(
            Cliente.tipo_cultivo,
            func.count(Gateway.id).label('total'),
            func.coalesce(func.sum(case((Gateway.status == 'UPDATED', 1), else_=0)), 0).label('act'),
            func.coalesce(func.sum(case((Gateway.status == 'PENDING', 1), else_=0)), 0).label('pend'),
            func.coalesce(func.sum(case((Gateway.status.in_(['OFFLINE', 'ERROR']), 1), else_=0)), 0).label('off'),
            func.coalesce(func.sum(case((Gateway.status == 'FROZEN_CARD', 1), else_=0)), 0).label('frozen')
        ).outerjoin(Gateway, Gateway.cliente_id == Cliente.id).group_by(Cliente.tipo_cultivo).all()

        cultivos = [{
            "tipo": r.tipo_cultivo or "Sin Asignar", 
            "total": int(r.total or 0), 
            "actualizados": int(r.act or 0), 
            "pendientes": int(r.pend or 0), 
            "offline": int(r.off or 0),
            "congelados": int(r.frozen or 0)
        } for r in stats]

        # 3. Top 10 Clientes con más fallos
        top = db.query(
            Cliente.nombre, 
            Cliente.tipo_cultivo,
            func.coalesce(func.sum(case((Gateway.status.in_(['OFFLINE', 'ERROR', 'FROZEN_CARD']), 1), else_=0)), 0).label('fallos'),
            func.count(Gateway.id).label('total')
        ).join(Gateway, Gateway.cliente_id == Cliente.id)\
         .group_by(Cliente.id, Cliente.nombre, Cliente.tipo_cultivo)\
         .order_by(desc('fallos'))\
         .limit(10).all()

        fallos = [{
            "nombre": r.nombre, 
            "cultivo": r.tipo_cultivo or "Sin Asignar", 
            "fallos": int(r.fallos or 0), 
            "total": int(r.total or 0)
        } for r in top if (r.fallos or 0) > 0]

        return {
            "globales": {
                "total": total, 
                "actualizados": act, 
                "pendientes": pend, 
                "offline": off,
                "congelados": frozen
            },
            "relay": {  # 🆕 NUEVO
                "con_relay": con_relay,
                "sin_relay": sin_relay,
                "sin_info": relay_null
            },
            "diagnosticos": {
                "mono_sin_espacio": diagnostic_counts.get("MONO_NO_SPACE", 0),
                "cartao_congelado": diagnostic_counts.get("FROZEN_CARD", 0)
            },
            "cultivos": cultivos,
            "top_fallos": fallos
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "globales": {"total": 0, "actualizados": 0, "pendientes": 0, "offline": 0, "congelados": 0},
            "relay": {"con_relay": 0, "sin_relay": 0, "sin_info": 0},
            "cultivos": [],
            "top_fallos": [],
            "error": str(e)
        }

@app.get("/api/reportes/actualizaciones_recientes")
async def get_actualizaciones_recientes(db: Session = Depends(get_db), limit: int = 20, _auth: bool = Depends(verify_api_key)):
    """Obtiene las últimas N actualizaciones realizadas"""
    actualizaciones = db.query(UpdateHistory, Gateway, Cliente).join(
        Gateway, UpdateHistory.gateway_ip == Gateway.ip
    ).outerjoin(
        Cliente, Gateway.cliente_id == Cliente.id
    ).order_by(UpdateHistory.timestamp.desc()).limit(limit).all()
    
    return [{
        "id": h.id,
        "gateway_ip": h.gateway_ip,
        "cliente": c.nombre if c else "Sin Asignar",
        "old_version": h.old_version,
        "new_version": h.new_version,
        "status": h.status,
        "duration_seconds": h.duration_seconds,
        "timestamp": serialize_datetime(h.timestamp),
        "error_message": h.error_message
    } for h, g, c in actualizaciones]

@app.get("/api/reportes/exportar_excel")
async def exportar_excel(db: Session = Depends(get_db), lang: str = "es", _auth: bool = Depends(verify_api_key)):
    gateways = db.query(Gateway, Cliente, Unidad).outerjoin(
        Cliente, Gateway.cliente_id == Cliente.id
    ).outerjoin(
        Unidad, Gateway.unidad_id == Unidad.id
    ).order_by(Cliente.nombre, Gateway.ip).all()

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})

    title = workbook.add_format({'bold': True, 'font_size': 18, 'font_color': 'white', 'bg_color': '#14532D', 'align': 'vcenter'})
    subtitle = workbook.add_format({'font_color': '#475569', 'italic': True})
    header = workbook.add_format({'bold': True, 'bg_color': '#166534', 'font_color': 'white', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
    label = workbook.add_format({'bold': True, 'bg_color': '#DCFCE7', 'font_color': '#14532D', 'border': 1})
    value = workbook.add_format({'align': 'center', 'border': 1})
    success = workbook.add_format({'bg_color': '#DCFCE7', 'font_color': '#166534', 'align': 'center', 'bold': True})
    pending = workbook.add_format({'bg_color': '#FEF3C7', 'font_color': '#92400E', 'align': 'center', 'bold': True})
    error_fmt = workbook.add_format({'bg_color': '#FEE2E2', 'font_color': '#991B1B', 'align': 'center', 'bold': True})
    relay_yes = workbook.add_format({'bg_color': '#DCFCE7', 'font_color': '#166534', 'align': 'center', 'bold': True})
    relay_no = workbook.add_format({'bg_color': '#FEE2E2', 'font_color': '#991B1B', 'align': 'center', 'bold': True})
    relay_unknown = workbook.add_format({'bg_color': '#E2E8F0', 'font_color': '#475569', 'align': 'center'})

    inventory_name = 'Inventario y Estado' if lang == 'es' else 'Inventário e Status'
    summary_name = 'Resumen' if lang == 'es' else 'Resumo'
    ws = workbook.add_worksheet(inventory_name)
    summary = workbook.add_worksheet(summary_name)
    ws.set_tab_color('#166534')
    summary.set_tab_color('#0F766E')

    headers = ['IP', 'Cliente', 'Unidad', 'Cultivo', 'Descripción', 'Flota', 'Relay LPWAN', 'Versión', 'SO', 'Estado', 'Último Escaneo', 'Última Actualización']
    if lang == 'pt':
        headers = ['IP', 'Cliente', 'Unidade', 'Cultivo', 'Descrição', 'Frota', 'Relay LPWAN', 'Versão', 'SO', 'Status', 'Última Varredura', 'Última Atualização']

    report_title = 'Reporte SolinfNet - Inventario y Estado' if lang == 'es' else 'Relatório SolinfNet - Inventário e Status'
    generated_label = 'Generado el' if lang == 'es' else 'Gerado em'
    ws.merge_range(0, 0, 0, len(headers) - 1, report_title, title)
    ws.write(1, 0, f"{generated_label}: {app_now().strftime('%Y-%m-%d %H:%M')}", subtitle)
    ws.set_row(0, 28)
    header_row = 3
    for col, heading in enumerate(headers):
        ws.write(header_row, col, heading, header)

    status_labels = {
        'UPDATED': 'Actualizado' if lang == 'es' else 'Atualizado',
        'PENDING': 'Pendiente' if lang == 'es' else 'Pendente',
        'OFFLINE': 'Offline',
        'ERROR': 'Error',
        'FROZEN_CARD': 'Necesario sustituir' if lang == 'es' else 'Necessário substituir',
    }

    for row, (gw, cl, un) in enumerate(gateways, start=header_row + 1):
        ws.write(row, 0, gw.ip)
        ws.write(row, 1, cl.nombre if cl else ('Sin Asignar' if lang == 'es' else 'Não Atribuído'))
        ws.write(row, 2, un.nombre if un else '-')
        ws.write(row, 3, cl.tipo_cultivo.upper() if cl else '-')
        ws.write(row, 4, gw.description or '-')
        ws.write(row, 5, gw.fleet_number or '-')
        if gw.has_relay is True:
            ws.write(row, 6, 'Sí' if lang == 'es' else 'Sim', relay_yes)
        elif gw.has_relay is False:
            ws.write(row, 6, 'No', relay_no)
        else:
            ws.write(row, 6, '-' if lang == 'es' else 'Sem informação', relay_unknown)
        ws.write(row, 7, gw.version or '-')
        ws.write(row, 8, gw.os_version or '-')

        estado = gw.status or '-'
        estado_visible = status_labels.get(estado, estado)
        if estado == 'UPDATED':
            ws.write(row, 9, estado_visible, success)
        elif estado == 'PENDING':
            ws.write(row, 9, estado_visible, pending)
        elif estado in ['OFFLINE', 'ERROR', 'FROZEN_CARD']:
            ws.write(row, 9, estado_visible, error_fmt)
        else:
            ws.write(row, 9, estado_visible)
        ws.write(row, 10, gw.last_scan.strftime('%Y-%m-%d %H:%M') if gw.last_scan else '-')
        ws.write(row, 11, gw.last_update.strftime('%Y-%m-%d %H:%M') if gw.last_update else '-')

    ws.autofilter(header_row, 0, header_row + len(gateways), len(headers) - 1)
    ws.freeze_panes(header_row + 1, 0)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)
    ws.repeat_rows(header_row)
    for col, width in zip('ABCDEFGHIJKL', [18, 25, 35, 12, 30, 10, 16, 12, 14, 24, 18, 18]):
        ws.set_column(f'{col}:{col}', width)

    total = len(gateways)
    updated = sum(gw.status == 'UPDATED' for gw, _, _ in gateways)
    pending_count = sum(gw.status == 'PENDING' for gw, _, _ in gateways)
    offline = sum(gw.status in ('OFFLINE', 'ERROR') for gw, _, _ in gateways)
    frozen = sum(gw.status == 'FROZEN_CARD' for gw, _, _ in gateways)
    with_relay = sum(gw.has_relay is True for gw, _, _ in gateways)
    without_relay = sum(gw.has_relay is False for gw, _, _ in gateways)
    summary_title = 'Resumen ejecutivo SolinfNet' if lang == 'es' else 'Resumo executivo SolinfNet'
    summary.merge_range('A1:D1', summary_title, title)
    summary.write('A2', f"{generated_label}: {app_now().strftime('%Y-%m-%d %H:%M')}", subtitle)
    summary.write_row('A4', ['Estado' if lang == 'es' else 'Status', 'Total'], header)
    summary_rows = [
        (status_labels['UPDATED'], updated),
        (status_labels['PENDING'], pending_count),
        ('Offline / Error', offline),
        (status_labels['FROZEN_CARD'], frozen),
    ]
    for row, (name, count) in enumerate(summary_rows, start=4):
        summary.write(row, 0, name, label)
        summary.write(row, 1, count, value)
    summary.write_row('A10', ['Indicador' if lang == 'es' else 'Indicador', 'Total'], header)
    relay_rows = [
        ('Gateways', total),
        ('Con Relay LPWAN' if lang == 'es' else 'Com Relay LPWAN', with_relay),
        ('Sin Relay LPWAN' if lang == 'es' else 'Sem Relay LPWAN', without_relay),
    ]
    for row, (name, count) in enumerate(relay_rows, start=10):
        summary.write(row, 0, name, label)
        summary.write(row, 1, count, value)
    chart = workbook.add_chart({'type': 'doughnut'})
    chart.add_series({
        'name': 'Estado' if lang == 'es' else 'Status',
        'categories': f"='{summary_name}'!$A$5:$A$8",
        'values': f"='{summary_name}'!$B$5:$B$8",
        'points': [{'fill': {'color': color}} for color in ['#16A34A', '#F59E0B', '#DC2626', '#BE123C']],
        'data_labels': {'percentage': True, 'category': True},
    })
    chart.set_title({'name': 'Estado de la flota' if lang == 'es' else 'Status da frota'})
    chart.set_legend({'position': 'bottom'})
    chart.set_style(10)
    summary.insert_chart('D4', chart, {'x_scale': 1.25, 'y_scale': 1.25})
    summary.set_column('A:A', 28)
    summary.set_column('B:B', 12)

    workbook.close()
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Reporte_SolinfNet.xlsx"}
    )


@app.post("/api/configure/{ip}")
async def start_configure(ip: str, _auth: bool = Depends(verify_api_key)):
    """Aplicar configuración estándar a un gateway (carpetas + LPWAN)"""
    ip = validate_ipv4(ip)
    from tasks import configure_gateway
    task = configure_gateway.delay(ip)
    return {"task_id": task.id, "ip": ip}

@app.get("/api/configure/status/{task_id}")
async def get_configure_status(task_id: str, _auth: bool = Depends(verify_api_key)):
    """Estado de tarea de configuración"""
    from tasks import configure_gateway
    task = configure_gateway.AsyncResult(task_id)
    if task.state == 'PENDING':
        return {"state": task.state, "step": 0, "message": "En cola...", "percent": 0}
    elif task.state == 'PROGRESS':
        return {
            "state": task.state, 
            "step": task.info.get('step', 0), 
            "message": task.info.get('message', ''), 
            "percent": task.info.get('percent', 0)
        }
    elif task.state == 'SUCCESS':
        return {"state": task.state, "result": task.result, "step": 7, "percent": 100}
    elif task.state == 'FAILURE':
        return {"state": task.state, "error": str(task.info), "step": 0, "percent": 0}
    else:
        return {"state": task.state}

@app.post("/api/install_mono/{ip}")
async def start_install_mono(ip: str, _auth: bool = Depends(verify_api_key)):
    """Instalar Mono 6.x en gateway con Debian 8/9"""
    ip = validate_ipv4(ip)
    from tasks import install_mono
    task = install_mono.delay(ip)
    return {"task_id": task.id, "ip": ip}

@app.get("/api/install_mono/status/{task_id}")
async def get_install_mono_status(task_id: str, _auth: bool = Depends(verify_api_key)):
    """Estado de instalación de Mono"""
    from tasks import install_mono
    task = install_mono.AsyncResult(task_id)
    if task.state == 'PENDING':
        return {"state": task.state, "step": 0, "message": "En cola...", "percent": 0}
    elif task.state == 'PROGRESS':
        return {
            "state": task.state,
            "step": task.info.get('step', 0),
            "message": task.info.get('message', ''),
            "percent": task.info.get('percent', 0)
        }
    elif task.state == 'SUCCESS':
        return {"state": task.state, "result": task.result, "step": 10, "percent": 100}
    elif task.state == 'FAILURE':
        return {"state": task.state, "error": str(task.info), "step": 0, "percent": 0}
    else:
        return {"state": task.state}


@app.get("/api/reportes/diagnosticos/{event_type}")
async def get_diagnostic_affected(event_type: str, db: Session = Depends(get_db), _auth: bool = Depends(verify_api_key)):
    """Devuelve gateways unicos afectados por un diagnostico operativo."""
    allowed = {
        "MONO_NO_SPACE": {
            "es": "Problemas Mono / espacio",
            "pt": "Problemas Mono / espaço",
        },
        "FROZEN_CARD": {
            "es": "Cartao congelado",
            "pt": "Cartão congelado",
        },
    }
    event_type = (event_type or "").upper()
    if event_type not in allowed:
        raise HTTPException(404, "Diagnóstico no soportado")

    if event_type == "MONO_NO_SPACE":
        incidents = [item for item in get_mono_incidents(db) if not item["resolved"]]
        latest_by_ip = {item["ip"]: item for item in incidents}
    else:
        events = db.query(GatewayDiagnosticEvent)\
            .filter(GatewayDiagnosticEvent.event_type == event_type)\
            .order_by(GatewayDiagnosticEvent.timestamp.desc())\
            .all()
        latest_by_ip = {}
        for event in events:
            if event.gateway_ip not in latest_by_ip:
                latest_by_ip[event.gateway_ip] = event

    frozen_event_ips = {ip for (ip,) in db.query(GatewayDiagnosticEvent.gateway_ip)\
        .filter(GatewayDiagnosticEvent.event_type == "FROZEN_CARD")\
        .distinct()\
        .all() if ip}
    current_frozen_ips = {ip for (ip,) in db.query(Gateway.ip).filter(Gateway.status == "FROZEN_CARD").all()}
    frozen_ips = frozen_event_ips | current_frozen_ips

    if event_type == "MONO_NO_SPACE":
        latest_by_ip = {ip: event for ip, event in latest_by_ip.items() if ip not in frozen_ips}
    elif event_type == "FROZEN_CARD":
        for ip in current_frozen_ips:
            latest_by_ip.setdefault(ip, None)

    gateways = db.query(Gateway).filter(Gateway.ip.in_(list(latest_by_ip.keys()))).all() if latest_by_ip else []
    clientes = {c.id: c for c in db.query(Cliente).all()}
    unidades = {u.id: u for u in db.query(Unidad).all()}
    gateways_by_ip = {g.ip: g for g in gateways}

    afectados = []
    for ip, event in latest_by_ip.items():
        gateway = gateways_by_ip.get(ip)
        cliente = clientes.get(gateway.cliente_id) if gateway and gateway.cliente_id else None
        unidad = unidades.get(gateway.unidad_id) if gateway and gateway.unidad_id else None
        incident = event if isinstance(event, dict) else None
        afectados.append({
            "ip": ip,
            "cliente_id": cliente.id if cliente else None,
            "cliente": cliente.nombre if cliente else None,
            "unidad_id": unidad.id if unidad else None,
            "unidad": unidad.nombre if unidad else None,
            "description": gateway.description if gateway else None,
            "version": gateway.version if gateway else None,
            "status": gateway.status if gateway else None,
            "has_relay": gateway.has_relay if gateway else None,
            "last_scan": serialize_datetime(gateway.last_scan) if gateway else None,
            "last_update": serialize_datetime(gateway.last_update) if gateway else None,
            "event_ts": incident["detected_at"] if incident else (serialize_datetime(event.timestamp) if event else None),
            "details": incident["details"] if incident else (event.details if event else None),
        })

    afectados.sort(key=lambda item: (item["cliente"] or "", item["unidad"] or "", item["ip"]))
    return {
        "event_type": event_type,
        "label": allowed[event_type],
        "total": len(afectados),
        "affected": afectados,
    }

@app.get("/api/cliente/{cliente_id}/detalle")
async def get_cliente_detalle(cliente_id: int, db: Session = Depends(get_db), _auth: bool = Depends(verify_api_key)):
    """Dossier ejecutivo de un cliente: KPIs, unidades, mini-mapa, historial."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")

    gateways = db.query(Gateway).filter(Gateway.cliente_id == cliente_id).all()
    unidades = db.query(Unidad).filter(Unidad.cliente_id == cliente_id).all()
    gw_por_unidad = {g.unidad_id: g for g in gateways if g.unidad_id}

    total        = len(gateways)
    actualizados = sum(1 for g in gateways if g.status == 'UPDATED')
    pendientes   = sum(1 for g in gateways if g.status == 'PENDING')
    offline      = sum(1 for g in gateways if g.status in ('OFFLINE', 'ERROR'))
    congelados   = sum(1 for g in gateways if g.status == 'FROZEN_CARD')
    con_relay    = sum(1 for g in gateways if g.has_relay is True)

    por_so = {}
    for g in gateways:
        por_so[g.os_version or "Sin dato"] = por_so.get(g.os_version or "Sin dato", 0) + 1

    detalle_unidades = []
    for u in unidades:
        g = gw_por_unidad.get(u.id)
        detalle_unidades.append({
            "id": u.id, "unidad": u.nombre, "ip": g.ip if g else None, "version": g.version if g else None,
            "status": g.status if g else "SIN_GATEWAY", "has_relay": g.has_relay if g else None,
            "os_version": g.os_version if g else None, "os_codename": g.os_codename if g else None,
            "description": g.description if g else None, "lat": g.latitude if g else None, "lon": g.longitude if g else None,
        })

    pines = [{"ip": g.ip, "status": g.status, "lat": g.latitude, "lon": g.longitude,
              "description": g.description, "fleet_number": g.fleet_number,
              "unidad": next((u.nombre for u in unidades if u.id == g.unidad_id), None)}
             for g in gateways if g.latitude and g.longitude]

    hist = db.query(UpdateHistory).join(Gateway, UpdateHistory.gateway_ip == Gateway.ip)\
             .filter(Gateway.cliente_id == cliente_id)\
             .order_by(UpdateHistory.timestamp.desc()).limit(8).all()
    mono_incidents = get_mono_incidents(db, cliente_id)

    return {
        "id": cliente.id, "nombre": cliente.nombre, "cultivo": cliente.tipo_cultivo, "subred": cliente.subred,
        "salud": round(actualizados / total * 100, 1) if total else 0,
        "kpis": {"total": total, "actualizados": actualizados, "pendientes": pendientes, "offline": offline, "congelados": congelados, "con_relay": con_relay},
        "por_so": por_so, "unidades": detalle_unidades, "pines": pines,
        "historial": [{"ip": h.gateway_ip, "op": h.old_version, "detalle": h.new_version,
                       "status": h.status, "ts": serialize_datetime(h.timestamp), "duracion": h.duration_seconds} for h in hist],
        "historial_mono": [{
            "ip": item["ip"], "detectado": item["detected_at"], "resuelto": item["resolved"],
            "fecha_resolucion": item["resolved_at"],
        } for item in mono_incidents[:12]],
    }

@app.get("/api/unidad/{unidad_id}/detalle")
async def get_unidad_detalle(unidad_id: int, gateway_ip: str = None, db: Session = Depends(get_db), _auth: bool = Depends(verify_api_key)):
    """Ficha técnica de una unidad/fazenda: su gateway, specs, mapa con contexto, historial."""
    u = db.query(Unidad).filter(Unidad.id == unidad_id).first()
    if not u:
        raise HTTPException(404, "Unidad no encontrada")
    cliente = db.query(Cliente).filter(Cliente.id == u.cliente_id).first()
    unit_gateways = db.query(Gateway).filter(Gateway.unidad_id == unidad_id)\
        .order_by(desc(Gateway.last_scan), Gateway.ip).all()
    gw = None
    if gateway_ip:
        gw = next((item for item in unit_gateways if item.ip == gateway_ip), None)
    if not gw and unit_gateways:
        gw = unit_gateways[0]

    gateways_unidad = [{
        "ip": item.ip, "version": item.version, "status": item.status,
        "description": item.description, "fleet_number": item.fleet_number,
        "lat": item.latitude, "lon": item.longitude,
        "is_primary": bool(gw and item.ip == gw.ip),
    } for item in unit_gateways]

    hist = []
    if gw:
        rows = db.query(UpdateHistory).filter(UpdateHistory.gateway_ip == gw.ip)\
                 .order_by(UpdateHistory.timestamp.desc()).limit(8).all()
        hist = [{"op": r.old_version, "detalle": r.new_version, "status": r.status,
                 "ts": serialize_datetime(r.timestamp), "duracion": r.duration_seconds} for r in rows]

    return {
        "unidad": {"id": u.id, "nombre": u.nombre},
        "cliente": {"id": cliente.id if cliente else None,
                    "nombre": cliente.nombre if cliente else None,
                    "cultivo": cliente.tipo_cultivo if cliente else None,
                    "subred": cliente.subred if cliente else None},
        "gateway": None if not gw else {
            "ip": gw.ip, "version": gw.version, "status": gw.status,
            "description": gw.description, "fleet_number": gw.fleet_number,
            "vid": gw.vid, "hardware_type": gw.hardware_type, "use_gps": gw.use_gps,
            "has_relay": gw.has_relay, "os_version": gw.os_version, "os_codename": gw.os_codename,
            "lat": gw.latitude, "lon": gw.longitude,
            "last_scan": serialize_datetime(gw.last_scan),
        },
        "gateways": gateways_unidad, "hermanos": [], "historial": hist,
    }
