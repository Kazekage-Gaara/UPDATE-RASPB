import re
import os
from database import SessionLocal
from models import Cliente, Unidad

db = SessionLocal()

print("=" * 70)
print("DIAGNÓSTICO COMPLETO DE UNIDADES")
print("=" * 70)

# 1. Verificar estado actual
total_clientes = db.query(Cliente).count()
total_unidades = db.query(Unidad).count()
print(f"\n📊 Estado actual de la BD:")
print(f"   Clientes: {total_clientes}")
print(f"   Unidades: {total_unidades}")

# 2. Si no hay unidades, ejecutar el parser con debug
if total_unidades == 0:
    print(f"\n🔧 No hay unidades. Ejecutando parser con debug...")
    
    base = '/app'
    archivos = [
        ('Preset Perenes IPs VPNs Solinftec.txt', 'perenes'),
        ('Preset Grãos IPs VPNs Solinftec.txt', 'graos'),
        ('Preset Cana IPs VPNs Solinftec.txt', 'cana'),
    ]
    
    def limpiar_nombre(raw):
        nombre = re.split(r'\t+', raw)[0]
        nombre = re.split(r'user\s*:', nombre, flags=re.IGNORECASE)[0]
        return nombre.strip()
    
    total_creadas = 0
    
    for fn, tipo in archivos:
        fp = os.path.join(base, fn)
        if not os.path.exists(fp):
            print(f"\n⚠️  Archivo no encontrado: {fp}")
            continue
        
        print(f"\n📄 Procesando: {fn}")
        
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        current_subred = None
        current_octetos = None
        creadas_archivo = 0
        lineas_procesadas = 0
        
        for i, line in enumerate(lines):
            s = line.strip()
            if not s or s.startswith('//') or s.startswith('Rotas'):
                continue
            
            lineas_procesadas += 1
            
            # Detectar subred
            m_sub = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:/\d{1,2})?\s+(.+)$', s)
            if m_sub:
                current_subred = m_sub.group(1)
                current_octetos = current_subred.split('.')[:2]
                continue
            
            # Detectar unidad (.5)
            m_uni = re.match(r'^(\d{1,3})\.5\s+(.+)$', s)
            if m_uni and current_subred and current_octetos:
                tercer = m_uni.group(1)
                nombre = limpiar_nombre(m_uni.group(2))
                ip_mk = f'{current_octetos[0]}.{current_octetos[1]}.{tercer}.5'
                
                # Buscar cliente
                cliente = db.query(Cliente).filter(Cliente.subred == current_subred).first()
                if not cliente:
                    cliente = db.query(Cliente).filter(Cliente.subred == current_subred + '/24').first()
                
                if cliente:
                    # Verificar si ya existe
                    existente = db.query(Unidad).filter(Unidad.ip == ip_mk).first()
                    if not existente:
                        nueva_unidad = Unidad(ip=ip_mk, nombre=nombre, cliente_id=cliente.id)
                        db.add(nueva_unidad)
                        creadas_archivo += 1
                        total_creadas += 1
                        
                        # Mostrar primeras 3 de cada archivo como ejemplo
                        if creadas_archivo <= 3:
                            print(f"   ✅ {ip_mk} -> {nombre[:40]} (cliente: {cliente.nombre})")
                    else:
                        if creadas_archivo <= 3:
                            print(f"   ⚠️  {ip_mk} ya existe")
                else:
                    if creadas_archivo == 0:
                        print(f"   ❌ No se encontró cliente para subred {current_subred}")
        
        print(f"   📈 Líneas procesadas: {lineas_procesadas}")
        print(f"   ✅ Unidades creadas: {creadas_archivo}")
    
    # Commit final
    print(f"\n💾 Guardando en base de datos...")
    try:
        db.commit()
        print(f"   ✅ Commit exitoso")
    except Exception as e:
        print(f"   ❌ Error en commit: {e}")
        db.rollback()
        print(f"   ↩️  Rollback ejecutado")

# 3. Verificar resultado final
total_final