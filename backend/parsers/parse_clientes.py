import re
import os
from database import SessionLocal
from models import Cliente, Gateway, Unidad

def _limpiar_nombre(raw):
    # Toma lo que hay antes del primer tabulador y/o antes de "user :"
    nombre = re.split(r'\t+', raw)[0]
    nombre = re.split(r'user\s*:', nombre, flags=re.IGNORECASE)[0]
    nombre = nombre.strip()
    return nombre


def reasociar_gateways_importados(db):
    """Aplica de inmediato los cambios de cliente/unidad de los TXT al inventario."""
    clientes_por_prefijo = {}
    for cliente in db.query(Cliente).all():
        octetos = (cliente.subred or '').split('.')
        if len(octetos) >= 2:
            clientes_por_prefijo[(octetos[0], octetos[1])] = cliente

    unidades_por_cliente_red = {}
    for unidad in db.query(Unidad).all():
        octetos = (unidad.ip or '').split('.')
        if len(octetos) >= 3:
            unidades_por_cliente_red[(unidad.cliente_id, octetos[2])] = unidad.id

    actualizados = 0
    for gateway in db.query(Gateway).all():
        octetos = (gateway.ip or '').split('.')
        if len(octetos) < 3:
            continue
        cliente = clientes_por_prefijo.get((octetos[0], octetos[1]))
        if not cliente:
            continue
        unidad_id = unidades_por_cliente_red.get((cliente.id, octetos[2]))
        if gateway.cliente_id != cliente.id or gateway.unidad_id != unidad_id:
            gateway.cliente_id = cliente.id
            gateway.unidad_id = unidad_id
            actualizados += 1
    return actualizados

def parse_clientes_file(filepath, tipo_cultivo):
    db = SessionLocal()
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        clientes_data = {}          # subred -> {nombre, ip_mikrotik}
        unidades_por_clave = {}     # (subred, tercer octeto) -> {ip, nombre, subred}
        current_subred = None
        current_octetos = None
        last_tercer = None

        for line in lines:
            s = line.strip()
            if not s or s.startswith('//') or s.startswith('Rotas'):
                continue

            # Subred (máscara /24 opcional)
            m_sub = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:/\d{1,2})?\s+(.+)$', s)
            if m_sub:
                current_subred = m_sub.group(1)
                current_octetos = current_subred.split('.')[:2]
                last_tercer = None
                if current_subred not in clientes_data:
                    clientes_data[current_subred] = {'nombre': m_sub.group(2).strip(), 'ip_mikrotik': None}
                continue

            # Unidad base: línea "N.5 Nombre ...". Tiene prioridad para nombrar la unidad/fazenda.
            m_uni = re.match(r'^(\d{1,3})\.5\s+(.+)$', s)
            if m_uni and current_subred and current_octetos:
                tercer = m_uni.group(1)
                last_tercer = tercer
                nombre = _limpiar_nombre(m_uni.group(2))
                if not nombre:
                    continue
                ip_mk = f"{current_octetos[0]}.{current_octetos[1]}.{tercer}.5"
                if current_subred in clientes_data and clientes_data[current_subred]['ip_mikrotik'] is None:
                    clientes_data[current_subred]['ip_mikrotik'] = ip_mk
                unidades_por_clave[(current_subred, tercer)] = {'ip': ip_mk, 'nombre': nombre, 'subred': current_subred}
                continue

            # Gateway/unidad directa: "N.105 Nombre" o ".105 Nombre". Se usa si no existe N.5.
            m_gw = re.match(r'^(?:(\d{1,3})?\.)?(?:10[5-9]|1[1-9]\d)\s+(.+)$', s)
            if m_gw and current_subred and current_octetos:
                tercer = m_gw.group(1) or last_tercer
                if not tercer:
                    continue
                last_tercer = tercer
                key = (current_subred, tercer)
                if key in unidades_por_clave:
                    continue
                nombre = _limpiar_nombre(m_gw.group(2))
                if not nombre:
                    continue
                ip_mk = f"{current_octetos[0]}.{current_octetos[1]}.{tercer}.5"
                if current_subred in clientes_data and clientes_data[current_subred]['ip_mikrotik'] is None:
                    clientes_data[current_subred]['ip_mikrotik'] = ip_mk
                unidades_por_clave[key] = {'ip': ip_mk, 'nombre': nombre, 'subred': current_subred}

        unidades_data = list(unidades_por_clave.values())

        # Upsert clientes
        for subred, data in clientes_data.items():
            ex = db.query(Cliente).filter(Cliente.subred == subred).first()
            if ex:
                ex.nombre = data['nombre']
                ex.tipo_cultivo = tipo_cultivo
                if data['ip_mikrotik'] and not ex.ip_mikrotik:
                    ex.ip_mikrotik = data['ip_mikrotik']
            else:
                db.add(Cliente(nombre=data['nombre'], tipo_cultivo=tipo_cultivo,
                               subred=subred, ip_mikrotik=data['ip_mikrotik']))

        # Upsert unidades
        for u in unidades_data:
            cliente = db.query(Cliente).filter(Cliente.subred == u['subred']).first()
            if not cliente:
                continue
            ex = db.query(Unidad).filter(Unidad.ip == u['ip']).first()
            if ex:
                ex.nombre = u['nombre']
                ex.cliente_id = cliente.id
            else:
                db.add(Unidad(ip=u['ip'], nombre=u['nombre'], cliente_id=cliente.id))

        db.commit()
        n_uni = db.query(Unidad).join(Cliente).filter(Cliente.tipo_cultivo == tipo_cultivo).count()
        print(f"✅ {os.path.basename(filepath)}: {len(clientes_data)} clientes / {len(unidades_data)} unidades procesadas")
        return len(clientes_data)
    except Exception as e:
        db.rollback()
        print(f"❌ Error parseando {os.path.basename(filepath)}: {e}")
        import traceback; traceback.print_exc()
        return 0
    finally:
        db.close()

def importar_todos_los_clientes(limpiar_previo=False):
    if limpiar_previo:
        db = SessionLocal()
        try:
            db.query(Unidad).delete()
            db.query(Cliente).delete()
            db.commit()
            print("🗑️  Tablas limpiadas")
        except Exception as e:
            db.rollback(); print(f"⚠️ {e}")
        finally:
            db.close()

    base_dir = os.path.dirname(os.path.dirname(__file__))
    archivos = [
        ('Preset Perenes IPs VPNs Solinftec.txt', 'perenes'),
        ('Preset Grãos IPs VPNs Solinftec.txt', 'graos'),
        ('Preset Cana IPs VPNs Solinftec.txt', 'cana'),
    ]
    total = 0
    for fn, tipo in archivos:
        p = os.path.join(base_dir, fn)
        total += parse_clientes_file(p, tipo) if os.path.exists(p) else 0

    db = SessionLocal()
    try:
        reasociados = reasociar_gateways_importados(db)
        db.commit()
        print(f"\n🎉 Clientes: {db.query(Cliente).count()} | Unidades: {db.query(Unidad).count()} | Gateways reasociados: {reasociados}")
    except Exception as e:
        db.rollback()
        print(f"⚠️ Error reasociando gateways tras importar presets: {e}")
    finally:
        db.close()
    return total

if __name__ == "__main__":
    from database import init_db
    init_db()
    importar_todos_los_clientes(limpiar_previo=('--clean' in __import__('sys').argv))
