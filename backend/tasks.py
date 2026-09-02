import os
import time
import subprocess
import re
import uuid
from contextvars import ContextVar
from functools import wraps
from datetime import datetime
from zoneinfo import ZoneInfo
from celery import Celery
from ssh_utils import run_ssh_command as raw_run_ssh_command, ping_host as raw_ping_host
from database import SessionLocal
from models import Gateway, UpdateHistory, GatewayDiagnosticEvent, Cliente, Unidad
from config import Config

redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
app = Celery('tasks', broker=redis_url, backend=redis_url)
APP_TIMEZONE = ZoneInfo("America/Sao_Paulo")
active_gateway_access = ContextVar("active_gateway_access", default=None)


def get_active_gateway_access():
    return active_gateway_access.get()


def run_ssh_command(ip: str, cmd: str, timeout: int = 15) -> dict:
    """Usa el NAT temporal solo dentro de una tarea LDC individual."""
    access = get_active_gateway_access()
    if access:
        return raw_run_ssh_command(access["rb_ip"], cmd, timeout=timeout, port=access["ssh_port"])
    return raw_run_ssh_command(ip, cmd, timeout=timeout)


def ping_host(ip: str) -> bool:
    access = get_active_gateway_access()
    if access:
        return raw_ping_host(access["rb_ip"], port=access["ssh_port"])
    return raw_ping_host(ip)


def with_gateway_access(func):
    """Aisla un acceso LDC temporal para que no afecte otras tareas Celery."""
    @wraps(func)
    def wrapped(self, ip: str, *args, **kwargs):
        access = kwargs.pop("access", None)
        token = active_gateway_access.set(access)
        try:
            return func(self, ip, *args, **kwargs)
        finally:
            active_gateway_access.reset(token)
    return wrapped


def app_now() -> datetime:
    """Mantiene las fechas de SQLite en la referencia horaria del panel."""
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)

def clean_solinfnet_version(value):
    """Extrae solo la version numerica aunque SSH imprima banners de login."""
    if not value:
        return ""
    text = str(value)
    match = re.search(r'Version:\s*([0-9]+(?:\.[0-9]+)+)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'\b([0-9]+(?:\.[0-9]+)+)\b', text)
    return match.group(1) if match else ""

def normalize_version(version):
    if not version: return ""
    cleaned = clean_solinfnet_version(version) or str(version)
    parts = cleaned.split('.')
    return f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else cleaned

def read_solinfnet_version(ip: str, attempts: int = 3, wait: float = 2.0) -> str:
    """Lee la versión del about.htm con reintentos (el servicio a veces tarda tras un reinicio)."""
    cmd = ("curl -s -u admin:admin -m 5 http://localhost:8085/about.htm 2>/dev/null "
           "| grep -oE 'Version: [0-9.]+' | awk '{print $2}' | head -1")
    for _ in range(attempts):
        res = run_ssh_command(ip, cmd, timeout=Config.SSH_TIMEOUT)
        output = (res.get("output") or "").strip() if res.get("success") else ""
        v = clean_solinfnet_version(output)
        if v:
            return v
        time.sleep(wait)
    return ""

def wait_for_ping(ip: str, timeout: int = 180, interval: int = 5) -> bool:
    """Espera un reboot real: primero debe caer el ping y luego volver."""
    start = time.time()
    saw_down = False
    time.sleep(5)
    while time.time() - start < timeout:
        is_up = ping_host(ip)
        if not is_up:
            saw_down = True
        elif saw_down:
            # Volvió a responder: dar tiempo extra para que servicios arranquen.
            time.sleep(15)
            return True
        time.sleep(interval)
    return False

def cleanup_runtime_artifacts(ip: str) -> dict:
    """Libera espacio de artefactos conocidos antes de operaciones que escriben temporales."""
    cmd = f"""
    FREE_BEFORE=$(df -Pm / 2>/dev/null | awk 'NR==2 {{print $4}}')
    CRASH_COUNT=$(find / -maxdepth 1 -type f -name 'mono_crash*' 2>/dev/null | wc -l)
    echo '{Config.RASP_PASSWORD}' | sudo -S find / -maxdepth 1 -type f -name 'mono_crash*' -delete 2>/dev/null || true
    rm -f /tmp/relay_block.txt /tmp/SolinfNet.conf.tmp /tmp/rootcron /tmp/rootcron.tmp 2>/dev/null || true
    FREE_AFTER=$(df -Pm / 2>/dev/null | awk 'NR==2 {{print $4}}')
    echo "MONO_CRASH_COUNT:$CRASH_COUNT"
    echo "FREE_MB_BEFORE:$FREE_BEFORE"
    echo "FREE_MB_AFTER:$FREE_AFTER"
    """
    res = run_ssh_command(ip, cmd, timeout=90)
    output = res.get("output", "") if res.get("success") else ""
    data = {"success": res.get("success", False), "output": output}
    for line in output.splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        data[key.strip().lower()] = value.strip()
    if output:
        print(f"[{ip}] Limpieza runtime: {output.strip().replace(chr(10), ' | ')}")
    elif not res.get("success"):
        print(f"[{ip}] Limpieza runtime falló: {res.get('error', '')}")
    crash_count = int(data.get('mono_crash_count') or 0)
    try:
        free_after = int(data.get('free_mb_after') or 0)
    except (TypeError, ValueError):
        free_after = 0
    if crash_count > 0:
        save_diagnostic_event(ip, "MONO_NO_SPACE", f"Se encontraron {crash_count} mono_crash; espacio libre despues: {free_after} MB")
        if data.get("success") and free_after > 100:
            save_diagnostic_event(
                ip,
                "MONO_SPACE_RESOLVED",
                f"Limpieza de mono_crash completada; espacio libre despues: {free_after} MB",
            )
    if free_after <= 100:
        save_diagnostic_event(ip, "LOW_DISK_SPACE", f"Solo quedan {free_after} MB libres despues de la limpieza")
    return data

def save_diagnostic_event(ip: str, event_type: str, details: str):
    db = SessionLocal()
    try:
        db.add(GatewayDiagnosticEvent(gateway_ip=ip, event_type=event_type, details=details))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[{ip}] Error guardando diagnostico {event_type}: {e}")
    finally:
        db.close()

def get_frozen_gateway(ip: str):
    """Evita que un escaneo normal borre el diagnostico de una SD congelada."""
    db = SessionLocal()
    try:
        gateway = db.query(Gateway).filter(Gateway.ip == ip).first()
        return gateway if gateway and gateway.status == "FROZEN_CARD" else None
    finally:
        db.close()

def prepare_persistence_probe(ip: str) -> str:
    token = f"{int(time.time())}_{os.getpid()}"
    cmd = f"printf '%s\n' '{token}' > /home/solinfnet/.update_persistence_probe && sync"
    res = run_ssh_command(ip, cmd, timeout=15)
    return token if res.get('success') else ""

def verify_persistence_probe(ip: str, token: str) -> str:
    """Confirma persistencia tras reboot sin confundir banners SSH con un fallo de SD."""
    if not token:
        return "NOT_VERIFIED"
    cmd = """
    if [ -f /home/solinfnet/.update_persistence_probe ]; then
        printf 'PERSISTENCE_PROBE:%s\\n' "$(cat /home/solinfnet/.update_persistence_probe)"
    else
        printf 'PERSISTENCE_PROBE:MISSING\\n'
    fi
    rm -f /home/solinfnet/.update_persistence_probe
    """
    for attempt in range(3):
        res = run_ssh_command(ip, cmd, timeout=15)
        output = res.get("output") or ""
        marker = re.search(r"PERSISTENCE_PROBE:([^\s]+)", output)
        if res.get("success") and marker:
            value = marker.group(1)
            if value == token:
                save_diagnostic_event(ip, "PERSISTENCE_OK", "Marcador sobrevivio al reinicio")
                return "OK"
            if value == "MISSING":
                save_diagnostic_event(ip, "FROZEN_CARD", "El marcador no sobrevivio al reinicio; posible cartao congelado")
                return "FROZEN"

            # Un marcador inesperado no demuestra que la tarjeta este congelada.
            break
        if attempt < 2:
            time.sleep(3)

    save_diagnostic_event(ip, "PERSISTENCE_UNVERIFIED", "No fue posible confirmar el marcador tras reboot; requiere nueva verificacion")
    return "UNVERIFIED"

PASSIVE_PERSISTENCE_PROBE_PATH = "/home/solinfnet/.scan_persistence_probe"

def get_passive_persistence_state(ip: str) -> dict:
    db = SessionLocal()
    try:
        gateway = db.query(Gateway).filter(Gateway.ip == ip).first()
        if not gateway:
            return {}
        return {
            "token": gateway.persistence_probe_token,
            "boot_id": gateway.persistence_probe_boot_id,
        }
    finally:
        db.close()

def read_passive_persistence_probe(ip: str) -> dict:
    """Lee el boot actual y el marcador sin alterar el gateway."""
    cmd = f"""
    BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || true)
    MARKER=$(cat {PASSIVE_PERSISTENCE_PROBE_PATH} 2>/dev/null || true)
    printf 'PASSIVE_BOOT_ID:%s\\nPASSIVE_MARKER:%s\\n' "$BOOT_ID" "$MARKER"
    """
    res = run_ssh_command(ip, cmd, timeout=15)
    output = res.get("output") or ""
    boot_match = re.search(r"PASSIVE_BOOT_ID:([0-9a-f-]+)", output, re.IGNORECASE)
    marker_match = re.search(r"PASSIVE_MARKER:([^\r\n]*)", output)
    if not res.get("success") or not boot_match:
        return {}
    return {
        "boot_id": boot_match.group(1).strip(),
        "marker": marker_match.group(1).strip() if marker_match else "",
    }

def write_passive_persistence_probe(ip: str) -> str:
    """Prepara una prueba para el proximo reinicio natural, sin reiniciar ahora."""
    token = f"scan-{uuid.uuid4().hex}"
    cmd = f"printf '%s\\n' '{token}' > {PASSIVE_PERSISTENCE_PROBE_PATH} && sync"
    res = run_ssh_command(ip, cmd, timeout=15)
    return token if res.get("success") else ""

def save_passive_persistence_state(ip: str, token: str = "", boot_id: str = "", verified: bool = False):
    if not token or not boot_id:
        return
    db = SessionLocal()
    try:
        gateway = db.query(Gateway).filter(Gateway.ip == ip).first()
        if not gateway:
            return
        gateway.persistence_probe_token = token
        gateway.persistence_probe_boot_id = boot_id
        gateway.persistence_probe_written_at = app_now()
        if verified:
            gateway.persistence_last_verified_at = app_now()
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[{ip}] Error guardando sonda pasiva de persistencia: {e}")
    finally:
        db.close()

def mark_frozen_from_passive_probe(ip: str):
    db = SessionLocal()
    try:
        gateway = db.query(Gateway).filter(Gateway.ip == ip).first()
        if not gateway:
            return
        gateway.status = "FROZEN_CARD"
        gateway.last_scan = app_now()
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[{ip}] Error marcando tarjeta congelada: {e}")
    finally:
        db.close()

def run_passive_persistence_probe(ip: str) -> dict:
    """Detecta reinicios naturales sin añadir reboot al flujo de escaneo."""
    current = read_passive_persistence_probe(ip)
    if not current:
        return {}

    previous = get_passive_persistence_state(ip)
    verified = False
    if previous.get("token") and previous.get("boot_id") and current["boot_id"] != previous["boot_id"]:
        if current.get("marker") != previous["token"]:
            save_diagnostic_event(
                ip,
                "FROZEN_CARD",
                "Marcador pasivo desaparecio despues de un reinicio detectado; posible cartao congelado",
            )
            mark_frozen_from_passive_probe(ip)
            return {"frozen": True}
        verified = True

    token = write_passive_persistence_probe(ip)
    return {"token": token, "boot_id": current["boot_id"], "verified": verified}

def _pref2(ip):
    p = ip.split('.')
    return f"{p[0]}.{p[1]}" if len(p) >= 2 else None

def _oct3(ip):
    p = ip.split('.')
    return p[2] if len(p) >= 3 else None

def asociar_gateway_a_cliente(ip, db):
    pref = _pref2(ip)
    if not pref: return None
    for c in db.query(Cliente).all():
        cp = c.subred.split('/')[0].split('.')
        if len(cp) >= 2 and f"{cp[0]}.{cp[1]}" == pref:
            return c.id
    return None

def asociar_gateway_a_unidad(ip, cliente_id, db):
    """Regla: misma subred del cliente + mismo TERCER octeto que la unidad (.5)."""
    if not cliente_id: return None
    to = _oct3(ip)
    if not to: return None
    for u in db.query(Unidad).filter(Unidad.cliente_id == cliente_id).all():
        up = u.ip.split('.')
        if len(up) >= 3 and up[2] == to:
            return u.id
    return None

@app.task(bind=True)
@with_gateway_access
def scan_and_check_version(self, ip: str, persist_failures: bool = True):
    """Verifica el gateway; en descubrimiento no registra candidatos fallidos."""
    TARGET_VERSION = Config.TARGET_VERSION
    TARGET_NORMALIZED = normalize_version(TARGET_VERSION)
    
    # Una SD congelada puede seguir respondiendo por SSH y parecer sana.
    # Solo una reinstalacion forzada debe volver a comprobar su persistencia.
    frozen_gateway = get_frozen_gateway(ip)
    if frozen_gateway:
        return {
            "ip": ip,
            "status": "FROZEN_CARD",
            "msg": "Cartao congelado - necessario substituir",
            "current_version": frozen_gateway.version,
            "diagnostic": "FROZEN_CARD",
        }

    if not ping_host(ip):
        unreachable_message = (
            "No responde al acceso SSH temporal de la RB"
            if get_active_gateway_access()
            else "No responde a Ping"
        )
        if persist_failures:
            save_gateway_status(ip, None, "OFFLINE")
        return {"ip": ip, "status": "OFFLINE", "msg": unreachable_message}

    # La sonda pasiva solo detecta un reboot que ya ocurrio; nunca reinicia ni
    # modifica la verificacion definitiva usada durante una actualizacion.
    passive_probe = run_passive_persistence_probe(ip)
    if passive_probe.get("frozen"):
        return {
            "ip": ip,
            "status": "FROZEN_CARD",
            "msg": "Cartao congelado detectado tras reinicio",
            "diagnostic": "FROZEN_CARD",
        }

    # Libera los crash de Mono antes de consultar SolinfNet: sin espacio el
    # servicio puede estar caido aunque el gateway siga respondiendo por SSH.
    cleanup_runtime_artifacts(ip)

    # 1. Obtener versión de SolinfNet (con reintentos)
    current_version = read_solinfnet_version(ip)
    if not current_version:
        ssh_ok = run_ssh_command(ip, "echo OK", timeout=Config.SSH_TIMEOUT).get("success", False)
        if persist_failures:
            save_gateway_status(ip, None, "ERROR")
            save_passive_persistence_state(ip, **passive_probe)
        if not ssh_ok:
            return {"ip": ip, "status": "ERROR", "msg": "SSH Falló (sin conexión al gateway)"}
        return {"ip": ip, "status": "ERROR", "msg": "Gateway accesible, pero SolinfNet no devolvió la versión tras 3 intentos"}
    current_normalized = normalize_version(current_version)
    
    # 2. 🆕 Extraer datos del SolinfNet.conf
    conf_data = extract_conf_data(ip)
    
    # 3. 🆕 Extraer versión del SO
    os_data = extract_os_version(ip)
    
    # 4. Determinar estado
    if current_normalized == TARGET_NORMALIZED:
        save_gateway_status(ip, current_version, "UPDATED", conf_data, os_data)
        save_passive_persistence_state(ip, **passive_probe)
        return {"ip": ip, "status": "UPDATED", "msg": f"OK - sin acción necesaria (versión {current_version})", "current_version": current_version}
    else:
        save_gateway_status(ip, current_version, "PENDING", conf_data, os_data)
        save_passive_persistence_state(ip, **passive_probe)
        return {"ip": ip, "status": "PENDING", "msg": f"🔄 Versión actual: {current_version} (necesita {TARGET_VERSION})", "current_version": current_version}

def _nmea_to_decimal(raw: str, direction: str):
    try:
        value = float(raw)
        if value == 0:
            return None

        degrees = int(value / 100)
        minutes = value - (degrees * 100)
        decimal = degrees + (minutes / 60)
        if direction.strip().upper() in ('S', 'W'):
            decimal = -decimal
        return decimal
    except (TypeError, ValueError):
        return None

def _parse_ttygps_coordinates(output: str):
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line.startswith('$'):
            continue

        body = line.split('*', 1)[0]
        fields = body.split(',')
        sentence = fields[0]

        if sentence in ('$GPRMC', '$GNRMC') and len(fields) >= 7 and fields[2] == 'A':
            lat = _nmea_to_decimal(fields[3], fields[4])
            lon = _nmea_to_decimal(fields[5], fields[6])
        elif sentence in ('$GPGGA', '$GNGGA') and len(fields) >= 7 and fields[6] not in ('', '0'):
            lat = _nmea_to_decimal(fields[2], fields[3])
            lon = _nmea_to_decimal(fields[4], fields[5])
        elif sentence in ('$GPGLL', '$GNGLL') and len(fields) >= 7 and fields[6] == 'A':
            lat = _nmea_to_decimal(fields[1], fields[2])
            lon = _nmea_to_decimal(fields[3], fields[4])
        else:
            continue

        if lat is not None and lon is not None:
            return {'latitude': lat, 'longitude': lon}

    return {}

def extract_ttygps_data(ip: str):
    """Lee una muestra corta de /dev/ttyGPS y extrae coordenadas NMEA con fix valido."""
    # El puerto serie no llega nunca a EOF. Salir al recibir el primer fix
    # valido evita que SSH quede esperando aunque timeout mate a cat.
    cmd = ("timeout 8 sh -c 'cat /dev/ttyGPS 2>/dev/null' | "
           "awk -F, '$1 == \"$GPRMC\" && $3 == \"A\" {print; exit} "
           "$1 == \"$GPGGA\" && $7 != \"0\" && $7 != \"\" {print; exit}'")
    res = run_ssh_command(ip, cmd, timeout=12)
    if not res["success"]:
        return {}
    return _parse_ttygps_coordinates(res.get("output", ""))

def extract_conf_data(ip: str):
    """Extrae datos del PRIMER BLOQUE del archivo SolinfNet.conf + detecta Relay LPWAN"""
    try:
        # Leer solo el primer bloque (gateway principal)
        cmd = "sed -n '1,/^End=/p' /home/solinfnet/SolinfNet.conf 2>/dev/null"
        res = run_ssh_command(ip, cmd, timeout=10)
        
        if not res["success"]:
            return {}
        
        conf_lines = res["output"].strip().split('\n')
        data = {}
        raw_lat = None
        raw_lon = None
        lat_dir = 'S'
        lon_dir = 'W'
        
        for line in conf_lines:
            line = line.strip()
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            if key == 'Description':
                data['description'] = value
            elif key == 'Server_GroupNumber':
                data['fleet_number'] = value
            elif key == 'MyLatitude':
                raw_lat = value
            elif key == 'MyLongitude':
                raw_lon = value
            elif key == 'MyLatitudeDir':
                lat_dir = value.strip().upper()
            elif key == 'MyLongitudeDir':
                lon_dir = value.strip().upper()
            elif key == 'VID':
                data['vid'] = value
            elif key == 'Hardware':
                data['hardware_type'] = value
            elif key == 'UseGPS':
                data['use_gps'] = value == '1'
        
        # Convertir coordenadas
        lat_decimal = _nmea_to_decimal(raw_lat, lat_dir)
        lon_decimal = _nmea_to_decimal(raw_lon, lon_dir)
        if lat_decimal is not None:
            data['latitude'] = lat_decimal
        if lon_decimal is not None:
            data['longitude'] = lon_decimal

        if data.get('use_gps') and ('latitude' not in data or 'longitude' not in data):
            data.update(extract_ttygps_data(ip))
        
        # Detectar Relay LPWAN con marcadores explicitos para no confundirse con banners SSH.
        cmd_relay = "grep -q 'Hardware = Relay' /home/solinfnet/SolinfNet.conf && echo RELAY_PRESENT || echo RELAY_ABSENT"
        res_relay = run_ssh_command(ip, cmd_relay, timeout=10)
        if res_relay["success"]:
            relay_output = res_relay.get("output", "")
            if "RELAY_PRESENT" in relay_output:
                data['has_relay'] = True
            elif "RELAY_ABSENT" in relay_output:
                data['has_relay'] = False
        
        # Debug
        if 'latitude' in data and 'longitude' in data:
            print(f"[{ip}] GPS: {data['latitude']:.5f}, {data['longitude']:.5f}")
        if 'description' in data:
            print(f"[{ip}] Descripción: {data['description']} | Flota: {data.get('fleet_number', 'N/A')} | Relay: {'Sí' if data.get('has_relay') else 'No'}")
        
        return data
    except Exception as e:
        print(f"Error extrayendo conf de {ip}: {e}")
        return {}

def relay_present_in_conf(ip: str, attempts: int = 3, wait: float = 2.0) -> bool | None:
    """Confirma presencia de Relay con marcadores estables; None indica lectura ambigua."""
    cmd_relay = "grep -q 'Hardware = Relay' /home/solinfnet/SolinfNet.conf && echo RELAY_PRESENT || echo RELAY_ABSENT"
    for attempt in range(attempts):
        res_relay = run_ssh_command(ip, cmd_relay, timeout=15)
        if res_relay.get("success"):
            relay_output = res_relay.get("output", "")
            if "RELAY_PRESENT" in relay_output:
                return True
            if "RELAY_ABSENT" in relay_output:
                return False
        if attempt < attempts - 1:
            time.sleep(wait)
    return None

def extract_os_version(ip: str):
    """Extrae la versión del sistema operativo"""
    try:
        # Intentar leer /etc/debian_version
        cmd = "cat /etc/debian_version 2>/dev/null || cat /etc/os-release 2>/dev/null | grep VERSION_ID | cut -d= -f2 | tr -d '\"'"
        res = run_ssh_command(ip, cmd, timeout=5)
        
        if not res["success"]:
            return {}
        
        version_str = res["output"].strip()
        if not version_str:
            return {}
        
        # Extraer número principal
        import re
        match = re.search(r'(\d+)', version_str)
        if match:
            version_num = match.group(1)
            
            # Mapear a nombres de Debian
            codenames = {
                '8': 'jessie',
                '9': 'stretch',
                '10': 'buster',
                '11': 'bullseye',
                '12': 'bookworm'
            }
            
            codename = codenames.get(version_num, 'unknown')
            return {
                'os_version': f"Debian {version_num}",
                'os_codename': codename
            }
        
        return {}
    except Exception as e:
        print(f"Error extrayendo OS de {ip}: {e}")
        return {}

def verificar_y_corregir_carpetas(ip: str) -> dict:
    """
    Verifica si las carpetas de log coinciden con la configuración
    y corrige automáticamente si hay discrepancia
    """
    try:
        # Verificar qué carpetas existen realmente
        cmd_check = """
        if [ -d "/home/solinfnet/Pluviometros" ]; then
            echo "PLUVIOMETROS"
        elif [ -d "/home/solinfnet/Meteorologia" ]; then
            echo "METEOROLOGIA"
        else
            echo "NINGUNA"
        fi
        """
        res = run_ssh_command(ip, cmd_check, timeout=10)
        if not res["success"]:
            return {"corregido": False, "error": "No se pudo verificar carpetas"}
        
        carpeta_real = res["output"].strip()
        
        if carpeta_real == "NINGUNA":
            return {"corregido": False, "mensaje": "No existe carpeta de logs"}
        
        # Verificar qué dice el conf
        cmd_conf = "grep 'LogFolder' /home/solinfnet/SolinfNet.conf | head -1"
        res_conf = run_ssh_command(ip, cmd_conf, timeout=10)
        if not res_conf["success"]:
            return {"corregido": False, "error": "No se pudo leer conf"}
        
        conf_line = res_conf["output"].strip()
        
        # Detectar discrepancia
        necesita_correccion = False
        if carpeta_real == "PLUVIOMETROS" and "Meteorologia" in conf_line:
            necesita_correccion = True
            carpeta_correcta = "Pluviometros"
        elif carpeta_real == "METEOROLOGIA" and "Pluviometros" in conf_line:
            necesita_correccion = True
            carpeta_correcta = "Meteorologia"
        
        if necesita_correccion:
            # Corregir el archivo de configuración
            cmd_fix = f"""
            sed -i 's|/home/solinfnet/Meteorologia|/home/solinfnet/{carpeta_correcta}|g' /home/solinfnet/SolinfNet.conf
            sed -i 's|/home/solinfnet/Pluviometros|/home/solinfnet/{carpeta_correcta}|g' /home/solinfnet/SolinfNet.conf
            echo "CORREGIDO"
            """
            res_fix = run_ssh_command(ip, cmd_fix, timeout=10)
            if res_fix["success"] and "CORREGIDO" in res_fix["output"]:
                return {"corregido": True, "carpeta": carpeta_correcta, "mensaje": f"Configuración corregida a {carpeta_correcta}"}
        
        return {"corregido": False, "mensaje": "Configuración correcta"}
        
    except Exception as e:
        return {"corregido": False, "error": str(e)}


def configurar_relay_lpwan(ip: str) -> dict:
    """
    Configura automáticamente el RELAY LPWAN si el gateway tiene antenas LPWAN.
    Versión robusta usando heredoc + archivo temporal.
    """
    try:
        cleanup_info = cleanup_runtime_artifacts(ip)
        try:
            free_after = int(cleanup_info.get('free_mb_after') or 0)
        except (TypeError, ValueError):
            free_after = 0
        if cleanup_info.get('success') and free_after <= 1:
            return {"configurado": False, "error": "Sin espacio libre tras limpiar mono_crash (disco lleno)"}

        # 1. Verificar si tiene Hardware RadioLocal (LPWAN)
        cmd_check = "grep -q 'Hardware = RadioLocal' /home/solinfnet/SolinfNet.conf && echo LPWAN_PRESENT || echo LPWAN_ABSENT"
        lpwan_output = ""
        for attempt in range(3):
            res = run_ssh_command(ip, cmd_check, timeout=10)
            lpwan_output = res.get("output", "") if res.get("success") else ""
            if res.get("success") and ("LPWAN_PRESENT" in lpwan_output or "LPWAN_ABSENT" in lpwan_output):
                break
            if attempt < 2:
                time.sleep(3)
        else:
            return {"configurado": False, "error": "No se pudo verificar LPWAN por SSH"}

        if "LPWAN_ABSENT" in lpwan_output:
            return {"configurado": False, "mensaje": "No tiene antenas LPWAN"}
        
        print(f"[{ip}] ✅ Tiene antenas LPWAN (RadioLocal)")
        
        # 2. Verificar si ya tiene Relay configurado sin confundirse con banners SSH.
        relay_state = relay_present_in_conf(ip, attempts=3, wait=3)
        if relay_state is None:
            return {"configurado": False, "error": "No se pudo verificar Relay existente por SSH"}
        print(f"[{ip}] Verificando Relay existente: {relay_state}")
        
        if relay_state:
            return {"configurado": False, "mensaje": "Relay ya configurado"}
        
        print(f"[{ip}] ✅ No tiene Relay - procediendo a configurarlo")
        
        # 3. Extraer valores del conf
        cmd_extract = """
        Server_Host=$(grep "Server_Host" /home/solinfnet/SolinfNet.conf | head -1 | cut -d'=' -f2 | tr -d ' ')
        Server_Port=$(grep "Server_Port" /home/solinfnet/SolinfNet.conf | head -1 | cut -d'=' -f2 | tr -d ' ')
        Server_User=$(grep "Server_User" /home/solinfnet/SolinfNet.conf | head -1 | cut -d'=' -f2 | tr -d ' ')
        Server_GroupNumber=$(tac /home/solinfnet/SolinfNet.conf | grep "Server_GroupNumber" | head -1 | cut -d'=' -f2 | tr -d ' ')
        WeatherStations=$(tac /home/solinfnet/SolinfNet.conf | grep "WeatherStations" | head -1 | cut -d'=' -f2 | tr -d ' ')
        VID=$(tac /home/solinfnet/SolinfNet.conf | grep "VID =" | grep -v "Tx_VID" | head -1 | cut -d'=' -f2 | tr -d ' ')
        echo "HOST:$Server_Host"
        echo "PORT:$Server_Port"
        echo "USER:$Server_User"
        echo "GROUP:$Server_GroupNumber"
        echo "WEATHER:$WeatherStations"
        echo "VID:$VID"
        """
        res_extract = run_ssh_command(ip, cmd_extract, timeout=15)
        if not res_extract["success"]:
            return {"configurado": False, "error": "No se pudieron extraer valores"}
        
        output = res_extract["output"]
        def extraer_valor(prefix):
            for line in output.split('\n'):
                if line.startswith(prefix + ':'):
                    return line.split(':', 1)[1]
            return ''
        
        host = extraer_valor('HOST')
        port = extraer_valor('PORT')
        user = extraer_valor('USER')
        group = extraer_valor('GROUP')
        weather = extraer_valor('WEATHER')
        vid = extraer_valor('VID')
        
        print(f"[{ip}] Valores extraídos: Host={host}, Port={port}, User={user}, Group={group}, VID={vid}")
        
        # 4. Backup del conf
        run_ssh_command(ip, "cp /home/solinfnet/SolinfNet.conf /home/solinfnet/SolinfNet.conf.backup.$(date +%Y%m%d_%H%M%S)", timeout=10)
        
        # 5. Incrementar todos los Index en 1 (excepto Index = 0)
        cmd_increment = """
        awk '
        /^Index = / {
            if ($3 != "0") {
                print "Index = " ($3 + 1)
            } else {
                print $0
            }
            next
        }
        { print }
        ' /home/solinfnet/SolinfNet.conf > /tmp/SolinfNet.conf.tmp && mv /tmp/SolinfNet.conf.tmp /home/solinfnet/SolinfNet.conf
        """
        run_ssh_command(ip, cmd_increment, timeout=10)
        
        # 6. Cambiar ServerType a RELAY para líneas después de la 55
        cmd_servertype = """
        awk 'NR > 55 && /^ServerType = / {
            print "ServerType = RELAY"
            next
        }
        { print }' /home/solinfnet/SolinfNet.conf > /tmp/SolinfNet.conf.tmp && mv /tmp/SolinfNet.conf.tmp /home/solinfnet/SolinfNet.conf
        """
        run_ssh_command(ip, cmd_servertype, timeout=10)
        
        # 7. Establecer RelayIndex = 1 para líneas después de la 55
        cmd_relayindex = """
        awk 'NR > 55 && /^RelayIndex = / {
            print "RelayIndex = 1"
            next
        }
        { print }' /home/solinfnet/SolinfNet.conf > /tmp/SolinfNet.conf.tmp && mv /tmp/SolinfNet.conf.tmp /home/solinfnet/SolinfNet.conf
        """
        run_ssh_command(ip, cmd_relayindex, timeout=10)
        
        # 8. 🔑 NUEVO: Crear archivo temporal con el bloque Relay usando HEREDOC
        # El heredoc preserva los saltos de línea perfectamente
        relay_block = f"""Index = 1
Hardware = Relay
Active = 1
Description = RELAY LPWAN
SendInstantIPDB = 1
InstantIPDBMaxRequests = 0
SendZIG33ToSNS = 1
MyLatitude =
MyLongitude =
VID = {vid}
TipoEquipo = 0
TipoServicio = 2
SSID = ZIGB6
SSIDInterval = 30
SSIDJumps = 4
RoutingMode = 2
PortName = /dev/ttyUSB0
PortSpeed = 9600
AllowAddLog = 1
LogFolder = /home/solinfnet/Meteorologia/LogGeral
AllowAddSerialLog = 1
SerialLogFolder = /home/solinfnet/Meteorologia/LogSerial
DBTempFolder = /home/solinfnet/Meteorologia/TempDB
MaxFilesPerFolder = 20000
ServerType = SNS
Server_Interface = gprs
Server_Host = {host}
Server_Port = {port}
Server_User = {user}
Server_Password = Gbt1sZd5vyMItLNHimkRXw==
Server_SendInterval = 10
Server_RxTimeout = 12
Server_TxTimeout = 12
Server_ErrorDelay = 10
Server_GroupNumber = {group}
SeftMonitorInterval = 120
Tx_PortName = /dev/tty
Tx_PortSpeed = 9600
Tx_VID = 0152
Tx_TipoEquipo =
TcpServer =
TcpPort = 4000
TcpAdminPort = 8085
TcpAdminUser = admin
TcpAdminPassword = admin
TcpAdminIndex = 0
BridgeTcpPort = 4000
BridgeSerialPortName = /dev/ttyAMA0
BridgeSerialPortSpeed = 115200
UseGPS = 1
RelayIndex = -1
Replicators =
WeatherStations = {weather}
KeepInContingencyMode = False
End=
"""
        
        # Escribir el bloque a un archivo temporal en el Raspberry usando heredoc
        cmd_create_file = f"""cat > /tmp/relay_block.txt << 'RELAYEOF'
{relay_block}RELAYEOF
"""
        res_create = run_ssh_command(ip, cmd_create_file, timeout=10)
        if not res_create["success"]:
            return {"configurado": False, "error": f"No se pudo crear archivo temporal: {res_create.get('error')}"}
        
        # 9. 🔑 NUEVO: Insertar el archivo después de la primera línea End= usando sed r (read)
        cmd_insert = """
        line_num=$(grep -n "^End=" /home/solinfnet/SolinfNet.conf | head -1 | cut -d: -f1)
        if [ -n "$line_num" ]; then
            sed -i "${line_num}r /tmp/relay_block.txt" /home/solinfnet/SolinfNet.conf
            rm -f /tmp/relay_block.txt
            echo "INSERTADO_LINEA_$line_num"
        else
            echo "ERROR_NO_END"
        fi
        """
        res_insert = run_ssh_command(ip, cmd_insert, timeout=15)
        
        if res_insert["success"] and "INSERTADO" in res_insert["output"]:
            # Verificar que realmente se insertó. Algunos gateways tardan unos
            # segundos en devolver una lectura limpia despues del sed.
            relay_state = relay_present_in_conf(ip, attempts=5, wait=2)
            print(f"[{ip}] Verificacion Relay tras insercion: {relay_state}")
            if relay_state is True:
                return {"configurado": True, "mensaje": f"RELAY LPWAN configurado (Host={host}, Grupo={group})"}
            
            return {"configurado": False, "error": "El bloque no se insertó correctamente"}
        else:
            error_msg = res_insert.get('output', res_insert.get('error', 'Desconocido'))
            return {"configurado": False, "error": f"No se pudo insertar bloque: {error_msg}"}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"configurado": False, "error": str(e)}


@app.task(bind=True)
def configure_gateway(self, ip: str):
    """
    Aplica configuración estándar al gateway (sin actualizar versión):
    1. Corrige carpetas Meteorologia/Pluviometros si hay discrepancia
    2. Configura RELAY LPWAN si el gateway tiene antenas
    3. Reinicia el servicio (o reboot si no hay servicio systemd)
    4. Verifica y actualiza metadatos en la BD
    """
    start_time = time.time()
    
    def update_progress(step, message, percent):
        self.update_state(state='PROGRESS', meta={
            'step': step, 'message': message, 'percent': percent, 'ip': ip
        })
        print(f"[{ip}][CONFIG] {step}: {message} ({percent}%)")
    
    print(f"\n{'='*60}\nINICIANDO CONFIGURACIÓN: {ip}\n{'='*60}")
    
    # 1. Verificar conectividad
    update_progress(1, "Verificando conectividad...", 10)
    if not ping_host(ip):
        save_operation_history(ip, "⚙️ CONFIGURAR", "Gateway offline", "FAILED", 0)
        return {"ip": ip, "status": "FAILED", "msg": "Gateway offline", "changes": []}
    
    cleanup_info = cleanup_runtime_artifacts(ip)
    crash_count = cleanup_info.get('mono_crash_count', '0')
    if crash_count not in ('0', ''):
        update_progress(1, f"Limpieza Mono: {crash_count} crash file(s)", 15)

    # 2. Extraer datos actuales del conf
    update_progress(2, "Leyendo configuración actual...", 20)
    conf_data = extract_conf_data(ip)
    
    # 3. Verificar y corregir carpetas
    update_progress(3, "Verificando carpetas Meteorologia/Pluviometros...", 40)
    resultado_carpetas = verificar_y_corregir_carpetas(ip)
    
    # 4. Configurar RELAY LPWAN si es necesario
    update_progress(4, "Verificando configuración LPWAN...", 60)
    resultado_lpwan = configurar_relay_lpwan(ip)
    if resultado_lpwan.get("error") and relay_present_in_conf(ip, attempts=3, wait=2) is True:
        resultado_lpwan = {
            "configurado": True,
            "mensaje": "Relay confirmado tras revalidación",
            "revalidated": True,
        }
    
    # 5. Determinar si hubo cambios
    changes = []
    if resultado_carpetas.get("corregido"):
        changes.append(f"Carpetas: {resultado_carpetas.get('carpeta')}")
    if resultado_lpwan.get("configurado"):
        changes.append("RELAY LPWAN agregado")
    if resultado_lpwan.get("error"):
        duration = int(time.time() - start_time)
        msg = f"Error configurando RELAY LPWAN: {resultado_lpwan.get('error')}"
        save_operation_history(ip, "⚙️ CONFIGURAR", msg, "FAILED", duration)
        return {"ip": ip, "status": "FAILED", "msg": msg, "changes": changes}
    
    # 6. 🔧 REINICIAR SERVICIO (o reboot si no hay servicio systemd)
    if changes:
        update_progress(5, "Verificando mecanismo de reinicio...", 70)
        
        # Detectar si existe el servicio systemd
        svc_check = run_ssh_command(ip, 
            "systemctl list-unit-files 2>/dev/null | grep -c 'solinfnet.service'", timeout=10)
        has_service = svc_check["success"] and svc_check["output"].strip() not in ("0", "")
        
        if has_service:
            # Gateway moderno: tiene servicio systemd → restart
            update_progress(5, "Reiniciando servicio SolinfNet (systemctl)...", 75)
            restart_cmd = f"echo '{Config.RASP_PASSWORD}' | sudo -S systemctl restart solinfnet"
            restart_res = run_ssh_command(ip, restart_cmd, timeout=20)
            
            if not restart_res["success"]:
                # Restart falló → fallback a reboot
                update_progress(5, "Restart falló → haciendo reboot...", 78)
                run_ssh_command(ip, f"echo '{Config.RASP_PASSWORD}' | sudo -S reboot", timeout=10)
                update_progress(5, "Esperando a que el gateway vuelva...", 80)
                if not wait_for_ping(ip, timeout=180):
                    save_operation_history(ip, "⚙️ CONFIGURAR", 
                                          f"{', '.join(changes)} - Gateway no volvió tras reboot", "FAILED", 
                                          int(time.time() - start_time))
                    return {"ip": ip, "status": "FAILED", 
                            "msg": "⚠️ Cambios aplicados pero gateway no volvió tras reboot", 
                            "changes": changes}
            else:
                time.sleep(5)
        else:
            # 🔑 Gateway antiguo: SIN servicio systemd → reboot directo (como v3)
            update_progress(5, "Sin servicio systemd → haciendo reboot...", 75)
            run_ssh_command(ip, f"echo '{Config.RASP_PASSWORD}' | sudo -S reboot", timeout=10)
            update_progress(5, "Esperando a que el gateway vuelva (puede tardar 1-3 min)...", 80)
            if not wait_for_ping(ip, timeout=180):
                save_operation_history(ip, "⚙️ CONFIGURAR", 
                                      f"{', '.join(changes)} - Gateway no volvió tras reboot", "FAILED", 
                                      int(time.time() - start_time))
                return {"ip": ip, "status": "FAILED", 
                        "msg": "⚠️ Cambios aplicados pero gateway no volvió tras reboot", 
                        "changes": changes}
        
        # 7. 🔧 VERIFICAR POR PUERTO (no por systemctl, que puede no existir)
        update_progress(6, "Verificando que SolinfNet responde...", 90)
        time.sleep(5)  # Dar tiempo extra para que el servicio arranque
        
        ver_res = run_ssh_command(ip, 
            "curl -s -u admin:admin -m 5 http://localhost:8085/about.htm 2>/dev/null | grep -oE 'Version: [0-9.]+' | head -1",
            timeout=15)
        
        if not ver_res["success"] or "Version:" not in ver_res.get("output", ""):
            # Segunda oportunidad (a veces tarda más en arrancar)
            time.sleep(10)
            ver_res = run_ssh_command(ip, 
                "curl -s -u admin:admin -m 5 http://localhost:8085/about.htm 2>/dev/null | grep -oE 'Version: [0-9.]+' | head -1",
                timeout=15)
            
            if not ver_res["success"] or "Version:" not in ver_res.get("output", ""):
                save_operation_history(ip, "⚙️ CONFIGURAR", 
                                      f"{', '.join(changes)} - SolinfNet no responde tras reinicio", "FAILED", 
                                      int(time.time() - start_time))
                return {"ip": ip, "status": "FAILED", 
                        "msg": "⚠️ Cambios aplicados pero SolinfNet no responde (verificar manualmente)", 
                        "changes": changes}
        
        # 8. 🔧 RE-EXTRAER DATOS DEL CONF (para actualizar has_relay en la BD)
        update_progress(7, "Actualizando metadatos en inventario...", 95)
        conf_data_new = extract_conf_data(ip)
        os_data = extract_os_version(ip)
        save_gateway_status(ip, None, None, conf_data_new, os_data)
        
        update_progress(8, "✅ Configuración completada", 100)
    else:
        update_progress(8, "✅ Sin cambios necesarios", 100)
    
    duration = int(time.time() - start_time)
    
    if changes:
        resumen = f"✅ {', '.join(changes)}"
        save_operation_history(ip, "⚙️ CONFIGURAR", resumen, "SUCCESS", duration)
        return {"ip": ip, "status": "SUCCESS",
                "msg": f"✅ Configurado: {', '.join(changes)} ({duration}s)",
                "duration": duration, "changes": changes}
    else:
        save_operation_history(ip, "⚙️ CONFIGURAR", "✅ Sin cambios necesarios", "SUCCESS", duration)
        return {"ip": ip, "status": "SUCCESS",
                "msg": f"✅ Configuración ya estaba correcta ({duration}s)",
                "duration": duration, "changes": []}


@app.task(bind=True)
@with_gateway_access
def update_gateway(self, ip: str, force: bool = False):
    """Tarea completa de actualización con verificación de SO y actualización de metadatos."""
    TARGET_VERSION = Config.TARGET_VERSION
    start_time = time.time()
    
    def update_progress(step, message, percent):
        self.update_state(state='PROGRESS', meta={
            'step': step, 'message': message, 'percent': percent, 'ip': ip
        })
        print(f"[{ip}] {step}: {message} ({percent}%)")
    
    action_label = "REINSTALACIÓN FORZADA" if force else "ACTUALIZACIÓN"
    print(f"\n{'='*60}\nINICIANDO {action_label}: {ip}\n{'='*60}")
    
    # 1. Verificar conectividad
    update_progress(1, "Verificando conectividad...", 5)
    if not ping_host(ip):
        unreachable_message = (
            "No responde al acceso SSH temporal de la RB"
            if get_active_gateway_access()
            else "Gateway offline"
        )
        save_gateway_status(ip, None, "OFFLINE")
        save_update_history(ip, None, TARGET_VERSION, "FAILED", 0, unreachable_message)
        return {"ip": ip, "status": "FAILED", "msg": unreachable_message}

    # 2. Limpiar antes de leer la versión. Con la raiz llena, SolinfNet puede
    # no arrancar y la consulta de about.htm devolveria "Desconocida".
    update_progress(2, "Liberando espacio y limpiando Mono...", 10)
    cleanup_info = cleanup_runtime_artifacts(ip)
    freed_before = cleanup_info.get('free_mb_before', '?')
    freed_after = cleanup_info.get('free_mb_after', '?')
    crash_count = cleanup_info.get('mono_crash_count', '0')
    if crash_count not in ('0', ''):
        update_progress(2, f"Limpieza Mono: {crash_count} crash file(s), libre {freed_before}->{freed_after} MB", 14)

    # 3. Verificar versión del sistema operativo antes de actualizar.
    update_progress(3, "Verificando versión del sistema operativo...", 15)
    os_data = extract_os_version(ip)

    # 4. Leer versión actual despues de liberar espacio.
    update_progress(4, "Leyendo versión actual...", 20)
    old_version = read_solinfnet_version(ip) or "Desconocida"

    # 3.5. 🚧 GATE: Debian < 10 requiere Mono suficiente
    # Confirmado: SolinfNet 6.5 corre con Mono 5.18 en Debian 8 (jessie)
    import re
    if os_data:
        m = re.search(r'Debian (\d+)', os_data.get('os_version', ''))
        debian_num = int(m.group(1)) if m else 99
        if debian_num < 10:
            update_progress(4, f"Debian {debian_num}: verificando Mono...", 21)
            mono_res = run_ssh_command(ip, "mono --version 2>/dev/null | head -1", timeout=10)
            mono_ver = mono_res["output"].strip() if mono_res["success"] else ""
            mono_major = 0
            mm = re.search(r'(\d+)', mono_ver)
            if mm:
                mono_major = int(mm.group(1))
            
            # Umbral: jessie=5 (confirmado: 5.18 sirve), stretch=5 (conservador)
            UMBRAL = 5
            
            if mono_major < UMBRAL:
                msg = (f"⚠️ Debian {debian_num} con Mono {mono_ver or 'NO instalado'}: "
                       f"SolinfNet {TARGET_VERSION} requiere Mono {UMBRAL}+. "
                       f"Instale Mono con el botón 📦 primero.")
                save_update_history(ip, old_version, TARGET_VERSION, "BLOCKED", 0, msg)
                return {"ip": ip, "status": "BLOCKED", "msg": msg}
            else:
                update_progress(4, f"Debian {debian_num} con Mono {mono_ver} ✓", 22)

    # Copiar archivos (tolerante a enlaces lentos: compresión + timeout amplio + reintentos)
    update_progress(4, "Copiando archivos...", 25)
    for idx, filename in enumerate(Config.UPDATE_FILES):
        local_path = f"{Config.UPDATES_DIR}/{filename}"
        remote_path = f"/home/solinfnet/{filename}"

        if not os.path.exists(local_path):
            save_gateway_status(ip, old_version, "ERROR", None, os_data)
            return {"ip": ip, "status": "FAILED", "msg": f"Archivo {filename} no existe en servidor"}

        access = get_active_gateway_access()
        scp_cmd = [
            "sshpass", "-p", Config.RASP_PASSWORD, "scp",
            "-C",                                  # compresión (clave en 10-30 kb/s)
            "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=10",
            "-o", "ServerAliveCountMax=3",
            "-o", "StrictHostKeyChecking=no",
        ]
        if access:
            scp_cmd.extend(["-P", str(access["ssh_port"])])
        scp_cmd.extend([
            local_path, f"{Config.SSH_USER}@{access['rb_ip'] if access else ip}:{remote_path}"
        ])

        ok = False
        last_err = ""
        for intento in range(1, 4):                # hasta 3 intentos
            try:
                result = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    ok = True
                    break
                last_err = (result.stderr or "").strip()[-200:]
            except subprocess.TimeoutExpired:
                last_err = f"timeout 300s (intento {intento})"
            print(f"[{ip}] scp {filename} intento {intento} falló: {last_err}")
            time.sleep(3 * intento)                # backoff: 3s, 6s

        if not ok:
            save_gateway_status(ip, old_version, "ERROR", None, os_data)
            return {"ip": ip, "status": "FAILED",
                    "msg": f"Error copiando {filename} tras 3 intentos: {last_err}"}

        progress_percent = 25 + int((idx + 1) / len(Config.UPDATE_FILES) * 15)
        update_progress(4, f"{filename} copiado ({idx+1}/{len(Config.UPDATE_FILES)})", progress_percent)
    
    # 5. Configuración remota
    update_progress(5, "Configurando sistema (permisos, crontab)...", 45)
    config_cmd = f"""
    chmod +x /home/solinfnet/*.sh 2>/dev/null || true
    mkdir -p /home/solinfnet/GeneralLog
    echo '{Config.RASP_PASSWORD}' | sudo -S chown -R solinfnet:solinfnet /home/solinfnet/GeneralLog 2>/dev/null || true
    
    INI="/home/solinfnet/SolinfNet.ini"
    if [ -f "$INI" ]; then
        grep -v "/home/solinfnet/GeneralLog" "$INI" | grep -v "GenerateLogFrames" > "${{INI}}.tmp" || true
        mv "${{INI}}.tmp" "$INI" || true
        echo "/home/solinfnet/GeneralLog" >> "$INI"
        echo "GenerateLogFrames" >> "$INI"
    fi
    
    echo '{Config.RASP_PASSWORD}' | sudo -S crontab -l > /tmp/rootcron 2>/dev/null || true
    grep -v -E "limpar_logs|renomear|removekijonull|check_webpage" /tmp/rootcron > /tmp/rootcron.tmp 2>/dev/null || true
    cat >> /tmp/rootcron.tmp << 'CRON'
@reboot sleep 30 && /home/solinfnet/limpar_logs.sh
@reboot sleep 40 && /home/solinfnet/renomear.sh
@reboot sleep 50 && /home/solinfnet/removekijonull.sh
@reboot sleep 60 && /home/solinfnet/check_webpage.sh
CRON
    echo '{Config.RASP_PASSWORD}' | sudo -S crontab /tmp/rootcron.tmp
    rm -f /tmp/rootcron*
    echo "CONFIG_OK"
    """
    
    config_res = run_ssh_command(ip, config_cmd, timeout=30)
    if not config_res["success"] or "CONFIG_OK" not in config_res["output"]:
        save_gateway_status(ip, old_version, "ERROR", None, os_data)
        return {"ip": ip, "status": "FAILED", "msg": "Error en configuración remota"}
    
    # 6. 🔧 REINICIO ROBUSTO: detectar si hay servicio systemd, si no → reboot (como v3)
    persistence_probe = prepare_persistence_probe(ip)
    persistence_status = "NOT_VERIFIED"
    update_progress(6, "Verificando mecanismo de reinicio...", 58)
    svc_check = run_ssh_command(ip, 
        "systemctl list-unit-files 2>/dev/null | grep -c 'solinfnet.service'", timeout=10)
    has_service = svc_check["success"] and svc_check["output"].strip() not in ("0", "")
    
    if has_service:
        # Gateway moderno: tiene servicio systemd → restart
        update_progress(6, "Reiniciando servicio SolinfNet (systemctl)...", 60)
        restart_cmd = f"echo '{Config.RASP_PASSWORD}' | sudo -S systemctl restart solinfnet"
        restart_res = run_ssh_command(ip, restart_cmd, timeout=20)
        
        if not restart_res["success"]:
            # Restart falló → fallback a reboot (como v3)
            update_progress(6, "Restart falló → haciendo reboot...", 62)
            run_ssh_command(ip, f"echo '{Config.RASP_PASSWORD}' | sudo -S reboot", timeout=10)
            update_progress(6, "Esperando a que el gateway vuelva...", 65)
            if not wait_for_ping(ip, timeout=180):
                save_gateway_status(ip, old_version, "OFFLINE", None, os_data)
                save_update_history(ip, old_version, TARGET_VERSION, "FAILED", 
                                    int(time.time() - start_time), "Gateway no volvió tras reboot (180s)")
                return {"ip": ip, "status": "FAILED", 
                        "msg": "⚠️ Gateway no volvió después del reboot (esperar 3 min y re-escanear)"}
            persistence_status = verify_persistence_probe(ip, persistence_probe)
        else:
            time.sleep(5)
            # Un restart del servicio no permite diagnosticar persistencia de la SD;
            # mantenemos el marcador para validarlo con un reboot controlado al final.
    else:
        # Gateway antiguo: SIN servicio systemd → reboot directo (como v3)
        update_progress(6, "Sin servicio systemd → haciendo reboot (como v3)...", 60)
        run_ssh_command(ip, f"echo '{Config.RASP_PASSWORD}' | sudo -S reboot", timeout=10)
        update_progress(6, "Esperando a que el gateway vuelva (puede tardar 1-3 min)...", 65)
        if not wait_for_ping(ip, timeout=180):
            save_gateway_status(ip, old_version, "OFFLINE", None, os_data)
            save_update_history(ip, old_version, TARGET_VERSION, "FAILED", 
                                int(time.time() - start_time), "Gateway no volvió tras reboot (180s)")
            return {"ip": ip, "status": "FAILED", 
                    "msg": "⚠️ Gateway no volvió después del reboot (esperar 3 min y re-escanear)"}
        persistence_status = verify_persistence_probe(ip, persistence_probe)
    
    # 7. Esperar inicio
    update_progress(7, "Esperando inicio del servicio...", 70)
    time.sleep(5)
    
    # 8. Verificar y corregir carpetas
    update_progress(8, "Verificando configuración de carpetas...", 75)
    resultado_carpetas = verificar_y_corregir_carpetas(ip)
    
    # 9. Configurar RELAY LPWAN si es necesario
    update_progress(9, "Verificando configuración LPWAN...", 80)
    resultado_lpwan = configurar_relay_lpwan(ip)
    lpwan_error = resultado_lpwan.get("error")
    relay_revalidated = False
    if lpwan_error and relay_present_in_conf(ip, attempts=3, wait=2) is True:
        relay_revalidated = True
        lpwan_error = None
        resultado_lpwan = {
            "configurado": True,
            "mensaje": "Relay confirmado tras revalidación",
            "revalidated": True,
        }
    
    # Si configuramos relay, reiniciar nuevamente
    if resultado_lpwan.get("configurado"):
        update_progress(9, "Reiniciando por cambios LPWAN...", 82)
        if has_service:
            run_ssh_command(ip, f"echo '{Config.RASP_PASSWORD}' | sudo -S systemctl restart solinfnet", timeout=20)
        else:
            run_ssh_command(ip, f"echo '{Config.RASP_PASSWORD}' | sudo -S reboot", timeout=10)
            wait_for_ping(ip, timeout=180)
        time.sleep(5)
    
    # 10. Verificar persistencia si el flujo solo reinicio el servicio.
    if persistence_status == "NOT_VERIFIED":
        update_progress(10, "Verificando persistencia de la SD con reboot...", 86)
        if not persistence_probe:
            persistence_probe = prepare_persistence_probe(ip)
        run_ssh_command(ip, f"echo '{Config.RASP_PASSWORD}' | sudo -S reboot", timeout=10)
        update_progress(10, "Esperando retorno tras reboot de persistencia...", 88)
        if not wait_for_ping(ip, timeout=180):
            save_gateway_status(ip, old_version, "OFFLINE", None, os_data)
            save_update_history(ip, old_version, TARGET_VERSION, "FAILED",
                                int(time.time() - start_time), "Gateway no volvió tras reboot de persistencia (180s)")
            return {"ip": ip, "status": "FAILED",
                    "msg": "⚠️ Gateway no volvió después del reboot de persistencia"}
        persistence_status = verify_persistence_probe(ip, persistence_probe)

    if persistence_status == "FROZEN":
        update_progress(10, "⚠️ Cartao congelado detectado", 90)
        post_reboot_version = read_solinfnet_version(ip, attempts=6, wait=5.0) or old_version
        post_conf_data = extract_conf_data(ip)
        duration = int(time.time() - start_time)
        save_gateway_status(ip, post_reboot_version, "FROZEN_CARD", post_conf_data, os_data)
        history_message = "Cartao congelado"
        if lpwan_error and not post_conf_data.get("has_relay"):
            history_message += "; Relay LPWAN pendiente"
            save_diagnostic_event(ip, "RELAY_CONFIGURATION_FAILED", lpwan_error)
        save_update_history(ip, old_version, TARGET_VERSION, "FAILED", duration, history_message)
        return {"ip": ip, "status": "FAILED",
                "msg": "⚠️ Cartao congelado detectado" + ("; Relay LPWAN pendiente" if lpwan_error else ""),
                "duration": duration, "diagnostic": "FROZEN_CARD",
                "version_after_reboot": post_reboot_version}

    # 11. 🔧 VERIFICAR POR PUERTO (no por systemctl, que puede no existir)
    update_progress(11, "Verificando que SolinfNet responde...", 90)
    ver_res = run_ssh_command(ip, 
        "curl -s -u admin:admin -m 5 http://localhost:8085/about.htm 2>/dev/null | grep -oE 'Version: [0-9.]+' | head -1",
        timeout=15)
    
    if not ver_res["success"] or "Version:" not in ver_res.get("output", ""):
        # Dar una segunda oportunidad (a veces tarda más en arrancar)
        time.sleep(10)
        ver_res = run_ssh_command(ip, 
            "curl -s -u admin:admin -m 5 http://localhost:8085/about.htm 2>/dev/null | grep -oE 'Version: [0-9.]+' | head -1",
            timeout=15)
        if not ver_res["success"] or "Version:" not in ver_res.get("output", ""):
            save_gateway_status(ip, old_version, "ERROR", None, os_data)
            save_update_history(ip, old_version, TARGET_VERSION, "FAILED",
                                int(time.time() - start_time), "SolinfNet no responde en puerto 8085 tras reinicio")
            return {"ip": ip, "status": "FAILED", 
                    "msg": "⚠️ Archivos copiados pero SolinfNet no responde (verificar manualmente)"}
    
    # 12. 🆕 RE-EXTRAER DATOS DEL CONF (para actualizar has_relay y otros metadatos)
    update_progress(12, "Actualizando metadatos del gateway...", 92)
    conf_data = extract_conf_data(ip)
    
    # 13. Verificar nueva versión. Después de reiniciar, about.htm puede tardar en reflejar la versión nueva.
    update_progress(13, "Verificando nueva versión...", 96)
    new_version = read_solinfnet_version(ip, attempts=10, wait=5.0) or "Desconocida"
    duration = int(time.time() - start_time)
    
    # 14. 🆕 GUARDAR TODO EN LA BD (incluyendo SO, Relay, Conf)
    if new_version == TARGET_VERSION or normalize_version(new_version) == normalize_version(TARGET_VERSION):
        save_gateway_status(ip, new_version, "UPDATED", conf_data, os_data)
        save_update_history(ip, old_version, new_version, "SUCCESS", duration, None)
        
        # Construir mensaje con automatizaciones aplicadas
        automatizaciones = []
        if resultado_carpetas.get("corregido"):
            automatizaciones.append(f"Carpetas: {resultado_carpetas.get('carpeta')}")
        if resultado_lpwan.get("configurado") or relay_revalidated:
            automatizaciones.append("Relay LPWAN")
        lpwan_warning = lpwan_error
        if lpwan_warning and not conf_data.get("has_relay"):
            save_diagnostic_event(ip, "RELAY_CONFIGURATION_FAILED", lpwan_warning)
        else:
            lpwan_warning = None
        
        msg_extra = f" | 🔧 {', '.join(automatizaciones)}" if automatizaciones else ""
        msg_warning = f" | ⚠️ Relay LPWAN no configurado: {lpwan_warning}" if lpwan_warning else ""
        
        update_progress(14, "✅ Actualización completada", 100)
        return {
            "ip": ip, 
            "status": "SUCCESS", 
            "msg": f"✅ Actualizado de {old_version} a {new_version}{msg_extra}{msg_warning}",
            "duration": duration,
            "automatizaciones": automatizaciones,
            "os_version": os_data.get('os_version') if os_data else None
        }
    else:
        save_gateway_status(ip, new_version if new_version != "Desconocida" else old_version, "PENDING", conf_data, os_data)
        save_update_history(ip, old_version, new_version, "FAILED", duration, f"Versión incorrecta: {new_version}")
        return {"ip": ip, "status": "FAILED", "msg": f"Versión incorrecta: {new_version}"}

def save_gateway_status(ip: str, version: str, status: str, conf_data: dict = None, os_data: dict = None):
    db = SessionLocal()
    try:
        gateway = db.query(Gateway).filter(Gateway.ip == ip).first()
        
        cliente_id = asociar_gateway_a_cliente(ip, db)
        uid = asociar_gateway_a_unidad(ip, cliente_id, db) if cliente_id else None
        
        if gateway:
            if version is not None:
                gateway.version = clean_solinfnet_version(version) or version
            if status is not None:
                gateway.status = status
            gateway.last_scan = app_now()
            if cliente_id: gateway.cliente_id = cliente_id
            if uid: gateway.unidad_id = uid
            if get_active_gateway_access():
                gateway.access_mode = "LDC_RB"
                gateway.ldc_unit = get_active_gateway_access().get("ldc_unit") or gateway.ldc_unit
                gateway.ldc_rb_ip = get_active_gateway_access().get("ldc_rb_ip") or get_active_gateway_access().get("rb_ip") or gateway.ldc_rb_ip
            
            # Guardar datos del conf
            if conf_data:
                gateway.description = conf_data.get('description')
                gateway.fleet_number = conf_data.get('fleet_number')
                gateway.latitude = conf_data.get('latitude')
                gateway.longitude = conf_data.get('longitude')
                gateway.vid = conf_data.get('vid')
                gateway.hardware_type = conf_data.get('hardware_type')
                gateway.use_gps = conf_data.get('use_gps')
                if 'has_relay' in conf_data:
                    gateway.has_relay = conf_data.get('has_relay')
            
            # Guardar datos del SO
            if os_data:
                gateway.os_version = os_data.get('os_version')
                gateway.os_codename = os_data.get('os_codename')
        else:
            gateway = Gateway(
                ip=ip,
                version=clean_solinfnet_version(version) or version,
                status=status or "UNKNOWN",
                last_scan=app_now(),
                cliente_id=cliente_id,
                unidad_id=uid,
                description=conf_data.get('description') if conf_data else None,
                fleet_number=conf_data.get('fleet_number') if conf_data else None,
                latitude=conf_data.get('latitude') if conf_data else None,
                longitude=conf_data.get('longitude') if conf_data else None,
                vid=conf_data.get('vid') if conf_data else None,
                hardware_type=conf_data.get('hardware_type') if conf_data else None,
                use_gps=conf_data.get('use_gps') if conf_data else None,
                has_relay=conf_data.get('has_relay') if conf_data else None,  # 🆕 NUEVO
                os_version=os_data.get('os_version') if os_data else None,
                os_codename=os_data.get('os_codename') if os_data else None,
                access_mode="LDC_RB" if get_active_gateway_access() else None,
                ldc_unit=get_active_gateway_access().get("ldc_unit") if get_active_gateway_access() else None,
                ldc_rb_ip=(get_active_gateway_access().get("ldc_rb_ip") or get_active_gateway_access().get("rb_ip")) if get_active_gateway_access() else None,
            )
            db.add(gateway)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error BD gateway {ip}: {e}")
    finally:
        db.close()

def save_update_history(ip, old_version, new_version, status, duration, error_message):
    db = SessionLocal()
    try:
        db.add(UpdateHistory(gateway_ip=ip, old_version=old_version, new_version=new_version,
                             status=status, duration_seconds=duration, error_message=error_message, timestamp=app_now()))
        if status == "SUCCESS":
            gw = db.query(Gateway).filter(Gateway.ip == ip).first()
            if gw: gw.last_update = app_now()
        db.commit()
    except Exception as e:
        db.rollback(); print(f"Error BD historial {ip}: {e}")
    finally:
        db.close()

def save_operation_history(ip, operacion, detalle, status, duration=0):
    """Registra operaciones (CONFIG/MONO) en el historial para el botón 📜."""
    db = SessionLocal()
    try:
        db.add(UpdateHistory(
            gateway_ip=ip,
            old_version=operacion,        # ej "📦 MONO" / "⚙️ CONFIGURAR"
            new_version=detalle[:200],    # resumen de lo hecho
            status=status,                # SUCCESS / FAILED / SKIPPED
            duration_seconds=duration,
            error_message=None if status == 'SUCCESS' else detalle[:500],
            timestamp=app_now()
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error historial op {ip}: {e}")
    finally:
        db.close()


@app.task(bind=True, time_limit=10800, soft_time_limit=10740, acks_late=True)
def install_mono(self, ip: str):
    """Instala Mono 6.x en Debian 8/9. Sobrevive a caídas de SSH (nohup + pidfile)."""
    import re
    start_time = time.time()

    def update_progress(step, message, percent):
        self.update_state(state='PROGRESS', meta={
            'step': step, 'message': message, 'percent': percent, 'ip': ip
        })
        print(f"[{ip}][MONO] {step}: {message} ({percent}%)")

    def finish(status, msg, duration=None):
        # Registrar en historial para trazabilidad (botón 📜)
        save_operation_history(ip, "📦 MONO", msg, status, duration or int(time.time() - start_time))
        return {"ip": ip, "status": status, "msg": msg, "duration": duration or int(time.time() - start_time)}

    print(f"\n{'='*60}\nINICIANDO INSTALACIÓN DE MONO: {ip}\n{'='*60}")

    # 1. Conectividad
    update_progress(1, "Verificando conectividad...", 5)
    if not ping_host(ip):
        return finish("FAILED", "Gateway offline")

    # 2. SO
    update_progress(2, "Verificando versión del SO...", 10)
    os_data = extract_os_version(ip)
    if not os_data:
        return finish("FAILED", "No se pudo detectar el SO")
    if os_data.get('os_codename') not in ['jessie', 'stretch']:
        return finish("SKIPPED", f"{os_data.get('os_version')} no requiere Mono manual")

    # 3. Subir script
    update_progress(3, "Enviando script de instalación...", 15)
    script_local = "/app/scripts/install_mono.sh" if os.path.exists("/app/scripts/install_mono.sh") else os.path.join(os.path.dirname(__file__), "scripts", "install_mono.sh")
    script_remote = "/tmp/install_mono.sh"
    scp_cmd = ["sshpass", "-p", Config.RASP_PASSWORD, "scp",
               "-o", "StrictHostKeyChecking=no",
               script_local, f"{Config.SSH_USER}@{ip}:{script_remote}"]
    try:
        r = subprocess.run(scp_cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return finish("FAILED", f"No se pudo enviar script: {r.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        return finish("FAILED", "Timeout enviando script")

    # 4. 🔑 LANZAMIENTO CORREGIDO: pidfile + nohup + env var (sin pkill, sin conflicto stdin)
    update_progress(4, "Lanzando instalación en background...", 20)
    launch_cmd = f"""
if [ -f /tmp/mono_install.pid ]; then
    OLD_PID=$(cat /tmp/mono_install.pid 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "ALREADY_RUNNING:$OLD_PID"
        exit 0
    fi
fi
chmod +x {script_remote}
rm -f /tmp/mono_install.log
MONO_SUDO_PASS='{Config.RASP_PASSWORD}' nohup {script_remote} </dev/null >/tmp/mono_install.log 2>&1 &
disown 2>/dev/null || true
sleep 2
if [ -f /tmp/mono_install.pid ] && kill -0 "$(cat /tmp/mono_install.pid 2>/dev/null)" 2>/dev/null; then
    echo "LAUNCHED"
else
    echo "LAUNCH_FAILED"
fi
"""
    launch_res = run_ssh_command(ip, launch_cmd, timeout=20)
    out = launch_res.get("output", "") if launch_res["success"] else ""
    print(f"[{ip}] Lanzamiento -> {out.strip()!r}")

    if "LAUNCH_FAILED" in out:
        return finish("FAILED", "No se pudo lanzar la instalación (verifica permisos/contraseña)")
    if "ALREADY_RUNNING" not in out and "LAUNCHED" not in out:
        return finish("FAILED", f"Respuesta inesperada al lanzar: {out.strip()[:120]}")

    # 5. POLLING por PID real (sin auto-coincidencia)
    MAX_WAIT = 3 * 60 * 60
    POLL = 30
    elapsed = 0
    last_step = ""

    while elapsed < MAX_WAIT:
        time.sleep(POLL)
        elapsed += POLL

        check_cmd = """
if [ -f /tmp/mono_install.log ]; then
    echo "LOG:$(grep -E '^(STEP|DONE):' /tmp/mono_install.log | tail -1)"
fi
if [ -f /tmp/mono_install.pid ]; then
    PID=$(cat /tmp/mono_install.pid 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then echo "RUNNING:1"; else echo "RUNNING:0"; fi
else
    echo "RUNNING:0"
fi
"""
        check_res = run_ssh_command(ip, check_cmd, timeout=15)
        if not check_res["success"]:
            print(f"[{ip}] ⚠️ Poll falló (red), reintentando... ({elapsed}s)")
            continue

        output = check_res["output"]
        is_running = "RUNNING:1" in output
        log_line = next((l[4:].strip() for l in output.split('\n') if l.startswith("LOG:")), "")

        if log_line.startswith("DONE:SUCCESS"):
            mono_ver = log_line.split(":", 2)[2] if log_line.count(":") >= 2 else "6.x"
            update_progress(10, f"✅ Mono instalado: {mono_ver}", 100)
            save_gateway_status(ip, None, None, None, extract_os_version(ip))
            return finish("SUCCESS", f"✅ Mono {mono_ver} instalado correctamente")

        if log_line.startswith("DONE:FAIL"):
            err = log_line.split(":", 2)[2] if log_line.count(":") >= 2 else "Error desconocido"
            return finish("FAILED", f"❌ {err}")

        if log_line.startswith("STEP:"):
            parts = log_line.split(":", 2)
            sn = parts[1] if len(parts) > 1 else "?"
            sm = parts[2] if len(parts) > 2 else "Procesando..."
            try:
                pct = 20 + min(int(sn) * 7, 75)
            except Exception:
                pct = 50
            if log_line != last_step:
                update_progress(int(sn) if sn.isdigit() else 5, sm, pct)
                last_step = log_line

        if not is_running and not log_line.startswith("DONE:"):
            return finish("FAILED", "El proceso terminó sin resultado (revise /tmp/mono_install.log en el gateway)")

        if elapsed % 300 == 0:
            print(f"[{ip}] ⏳ Aún instalando... ({elapsed//60} min)")

    return finish("TIMEOUT", "⏱️ Timeout 3h. La instalación puede seguir corriendo en el gateway.")
