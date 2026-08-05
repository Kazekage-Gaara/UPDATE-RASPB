import re
import os
from database import SessionLocal
from models import Cliente, Unidad

def _limpiar_nombre(raw):
    # Toma lo que hay antes del primer tabulador y/o antes de "user :"
    nombre = re.split(r'\t+', raw)[0]
    nombre = re.split(r'user\s*:', nombre, flags=re.IGNORECASE)[0]
    nombre = nombre.strip()
    return nombre

def parse_clientes_file(filepath, tipo_cultivo):
    db = SessionLocal()
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        clientes_data = {}          # subred -> {nombre, ip_mikrotik}
        unidades_data = []          # {ip, nombre, subred}
        current_subred = None
        current_octetos = None

        for line in lines:
            s = line.strip()
            if not s or s.startswith('//') or s.startswith('Rotas'):
                continue

            # Subred (máscara /24 opcional)
            m_sub = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:/\d{1,2})?\s+(.+)$', s)
            if m_sub:
                current_subred = m_sub.group(1)
                current_octetos = current_subred.split('.')[:2]
                if current_subred not in clientes_data:
                    clientes_data[current_subred] = {'nombre': m_sub.group(2).strip(), 'ip_mikrotik': None}
                continue

            # Unidad: línea "N.5  Nombre ..."  (N = tercer octeto)
            m_uni = re.match(r'^(\d{1,3})\.5\s+(.+)$', s)
            if m_uni and current_subred and current_octetos:
                tercer = m_uni.group(1)
                nombre = _limpiar_nombre(m_uni.group(2))
                if not nombre:
                    continue
                ip_mk = f"{current_octetos[0]}.{current_octetos[1]}.{tercer}.5"
                if current_subred in clientes_data and clientes_data[current_subred]['ip_mikrotik'] is None:
                    clientes_data[current_subred]['ip_mikrotik'] = ip_mk
                unidades_data.append({'ip': ip_mk, 'nombre': nombre, 'subred': current_subred})

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

        # Upsert unidades (solo las .5)
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
        print(f"\n🎉 Clientes: {db.query(Cliente).count()} | Unidades: {db.query(Unidad).count()}")
    finally:
        db.close()
    return total

if __name__ == "__main__":
    from database import init_db
    init_db()
    importar_todos_los_clientes(limpiar_previo=('--clean' in __import__('sys').argv))