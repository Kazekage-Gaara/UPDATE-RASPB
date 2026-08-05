from database import SessionLocal
from models import Gateway, Cliente, Unidad

db = SessionLocal()

print(f"Total unidades en BD: {db.query(Unidad).count()}")
print(f"Total clientes en BD: {db.query(Cliente).count()}")
print(f"Total gateways en BD: {db.query(Gateway).count()}")
print("=" * 60)

asoc_c = 0
asoc_u = 0

for g in db.query(Gateway).all():
    p = g.ip.split('.')
    if len(p) < 3:
        print(f"  ⚠️  {g.ip}: IP malformada")
        continue

    pref = f"{p[0]}.{p[1]}"
    to = int(p[2])  # tercer octeto del gateway

    # --- Buscar cliente por prefijo de 2 octetos ---
    cid = None
    cname = None
    for c in db.query(Cliente).all():
        cp = c.subred.split('/')[0].split('.')
        if len(cp) >= 2 and f"{cp[0]}.{cp[1]}" == pref:
            cid = c.id
            cname = c.nombre
            break

    # --- Buscar unidad por cliente + tercer octeto ---
    uid = None
    uname = None
    unidades_cliente = []
    if cid:
        for u in db.query(Unidad).filter(Unidad.cliente_id == cid).all():
            up = u.ip.split('.')
            u_oct = int(up[2]) if len(up) >= 3 else None
            unidades_cliente.append((u.ip, u_oct, u.nombre))
            if u_oct == to:
                uid = u.id
                uname = u.nombre
                break

    g.cliente_id = cid
    g.unidad_id = uid
    if cid:
        asoc_c += 1
    if uid:
        asoc_u += 1

    print(f"  {g.ip} -> cliente={cname} (id={cid}) | 3er_oct={to} | unidad={uname} (id={uid})")

    # Si tiene cliente pero NO encontró unidad, mostrar las unidades disponibles para diagnosticar
    if cid and not uid:
        print(f"      ❌ Sin match. Unidades de {cname} (ip, 3er_oct, nombre):")
        for ui in unidades_cliente[:15]:
            print(f"         {ui}")

db.commit()
print("=" * 60)
print(f"✅ Gateways con cliente: {asoc_c} | con unidad: {asoc_u} / {db.query(Gateway).count()}")
db.close()
