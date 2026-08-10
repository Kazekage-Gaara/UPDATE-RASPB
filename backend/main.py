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
import os, io, xlsxwriter, secrets, ipaddress, threading, time, sqlite3

app = FastAPI(title="SolinfNet Control Center")
templates = Jinja2Templates(directory=".")
update_tasks = {}

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
    today = datetime.now().strftime("%Y%m%d")
    if not force:
        existing_today = [
            name for name in os.listdir(Config.DB_BACKUP_DIR)
            if name.startswith(f"solinfnet-{today}-") and name.endswith(".db")
        ]
        if existing_today:
            cleanup_old_database_backups()
            return os.path.join(Config.DB_BACKUP_DIR, sorted(existing_today)[-1])

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
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
        "last_scan": g.last_scan.isoformat() if g.last_scan else None,
        "last_update": g.last_update.isoformat() if g.last_update else None,
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
             "timestamp": x.timestamp.isoformat()} for x in h]

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
        update_tasks[t.id] = {"ip": ip, "started_at": datetime.now(), "force": force}
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
    now = datetime.now()

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

@app.get("/api/reportes/dashboard")
async def get_dashboard_data(db: Session = Depends(get_db), _auth: bool = Depends(verify_api_key)):
    """Obtiene las estadísticas para los gráficos del dashboard"""
    try:
        # 1. Totales globales
        total = db.query(Gateway).count()
        act = db.query(Gateway).filter(Gateway.status == 'UPDATED').count()
        pend = db.query(Gateway).filter(Gateway.status == 'PENDING').count()
        off = db.query(Gateway).filter(Gateway.status.in_(['OFFLINE', 'ERROR'])).count()
        
        # 🆕 NUEVO: Estadísticas de Relay LPWAN
        con_relay = db.query(Gateway).filter(Gateway.has_relay == True).count()
        sin_relay = db.query(Gateway).filter(Gateway.has_relay == False).count()
        relay_null = db.query(Gateway).filter(Gateway.has_relay == None).count()

        diagnostic_rows = db.query(GatewayDiagnosticEvent.event_type, GatewayDiagnosticEvent.gateway_ip)\
            .filter(GatewayDiagnosticEvent.event_type.in_(["MONO_NO_SPACE", "FROZEN_CARD"]))\
            .distinct()\
            .all()
        diagnostic_ips = {"MONO_NO_SPACE": set(), "FROZEN_CARD": set()}
        for event_type, gateway_ip in diagnostic_rows:
            if event_type in diagnostic_ips and gateway_ip:
                diagnostic_ips[event_type].add(gateway_ip)
        current_frozen_ips = {ip for (ip,) in db.query(Gateway.ip).filter(Gateway.status == "FROZEN_CARD").all()}
        frozen_ips = diagnostic_ips["FROZEN_CARD"] | current_frozen_ips
        diagnostic_counts = {
            "MONO_NO_SPACE": len(diagnostic_ips["MONO_NO_SPACE"] - frozen_ips),
            "FROZEN_CARD": len(frozen_ips),
        }

        # 2. Estadísticas por Tipo de Cultivo
        stats = db.query(
            Cliente.tipo_cultivo,
            func.count(Gateway.id).label('total'),
            func.coalesce(func.sum(case((Gateway.status == 'UPDATED', 1), else_=0)), 0).label('act'),
            func.coalesce(func.sum(case((Gateway.status == 'PENDING', 1), else_=0)), 0).label('pend'),
            func.coalesce(func.sum(case((Gateway.status.in_(['OFFLINE', 'ERROR']), 1), else_=0)), 0).label('off')
        ).outerjoin(Gateway, Gateway.cliente_id == Cliente.id).group_by(Cliente.tipo_cultivo).all()

        cultivos = [{
            "tipo": r.tipo_cultivo or "Sin Asignar", 
            "total": int(r.total or 0), 
            "actualizados": int(r.act or 0), 
            "pendientes": int(r.pend or 0), 
            "offline": int(r.off or 0)
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
                "offline": off
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
            "globales": {"total": 0, "actualizados": 0, "pendientes": 0, "offline": 0},
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
        "timestamp": h.timestamp.isoformat(),
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

    header = workbook.add_format({'bold': True, 'bg_color': '#2D5016', 'font_color': 'white', 'border': 1, 'align': 'center'})
    success = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100', 'align': 'center'})
    pending = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C6500', 'align': 'center'})
    error_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'align': 'center'})
    relay_yes = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100', 'align': 'center'})
    relay_no = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'align': 'center'})

    ws = workbook.add_worksheet('Inventario y Estado')
    
    headers = ['IP', 'Cliente', 'Unidad', 'Cultivo', 'Descripción', 'Flota', 'Relay LPWAN', 'Versión', 'SO', 'Estado', 'Último Escaneo', 'Última Actualización']
    if lang == 'pt':
        headers = ['IP', 'Cliente', 'Unidade', 'Cultivo', 'Descrição', 'Frota', 'Relay LPWAN', 'Versão', 'SO', 'Status', 'Última Varredura', 'Última Atualização']
        
    for col, h in enumerate(headers):
        ws.write(0, col, h, header)

    for row, (gw, cl, un) in enumerate(gateways, start=1):
        ws.write(row, 0, gw.ip)
        ws.write(row, 1, cl.nombre if cl else ('Sin Asignar' if lang=='es' else 'Não Atribuído'))
        ws.write(row, 2, un.nombre if un else '-')
        ws.write(row, 3, cl.tipo_cultivo.upper() if cl else '-')
        ws.write(row, 4, gw.description or '-')
        ws.write(row, 5, gw.fleet_number or '-')
        
        # 🆕 Relay LPWAN
        if gw.has_relay is True:
            ws.write(row, 6, '✅ Sí' if lang == 'es' else '✅ Sim', relay_yes)
        elif gw.has_relay is False:
            ws.write(row, 6, '❌ No', relay_no)
        else:
            ws.write(row, 6, '❓')
        
        ws.write(row, 7, gw.version or '-')
        ws.write(row, 8, gw.os_version or '-')
        
        estado = gw.status or '-'
        if estado == 'UPDATED': ws.write(row, 9, estado, success)
        elif estado == 'PENDING': ws.write(row, 9, estado, pending)
        elif estado in ['OFFLINE', 'ERROR', 'FROZEN_CARD']: ws.write(row, 9, estado, error_fmt)
        else: ws.write(row, 9, estado)
        
        ws.write(row, 10, gw.last_scan.strftime('%Y-%m-%d %H:%M') if gw.last_scan else '-')
        ws.write(row, 11, gw.last_update.strftime('%Y-%m-%d %H:%M') if gw.last_update else '-')

    ws.autofilter(0, 0, len(gateways), len(headers) - 1)
    for col, w in zip('ABCDEFGHIJKL', [18, 25, 35, 12, 30, 10, 12, 10, 12, 12, 18, 18]):
        ws.set_column(f'{col}:{col}', w)
    
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
            "last_scan": gateway.last_scan.isoformat() if gateway and gateway.last_scan else None,
            "last_update": gateway.last_update.isoformat() if gateway and gateway.last_update else None,
            "event_ts": event.timestamp.isoformat() if event and event.timestamp else None,
            "details": event.details if event else None,
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

    return {
        "id": cliente.id, "nombre": cliente.nombre, "cultivo": cliente.tipo_cultivo, "subred": cliente.subred,
        "salud": round(actualizados / total * 100, 1) if total else 0,
        "kpis": {"total": total, "actualizados": actualizados, "pendientes": pendientes, "offline": offline, "congelados": congelados, "con_relay": con_relay},
        "por_so": por_so, "unidades": detalle_unidades, "pines": pines,
        "historial": [{"ip": h.gateway_ip, "op": h.old_version, "detalle": h.new_version,
                       "status": h.status, "ts": h.timestamp.isoformat(), "duracion": h.duration_seconds} for h in hist],
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
                 "ts": r.timestamp.isoformat(), "duracion": r.duration_seconds} for r in rows]

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
            "last_scan": gw.last_scan.isoformat() if gw.last_scan else None,
        },
        "gateways": gateways_unidad, "hermanos": [], "historial": hist,
    }
