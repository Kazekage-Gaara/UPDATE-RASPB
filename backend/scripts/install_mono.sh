#!/bin/bash
# Instalación Mono 6.x (Debian 8/9) - ALINEADO con actualizar_solinfnet_v3.sh
# Corre desacoplado (setsid). Contraseña sudo por env var MONO_SUDO_PASS.
# Escribe progreso como STEP:N:mensaje / DONE:SUCCESS|FAIL:mensaje
export DEBIAN_FRONTEND=noninteractive
LOG="/tmp/mono_install.log"
PASS="${MONO_SUDO_PASS:-}"

: > "$LOG"
exec >>"$LOG" 2>&1          # desacopla stdout del canal SSH
echo $$ > /tmp/mono_install.pid

# sudo sin conflicto de stdin (la contraseña va por pipe; el cmd NO lee stdin)
dsudo() { echo "$PASS" | sudo -S -p '' "$@"; }
step() { echo "STEP:$1:$2"; }
fail() { echo "DONE:FAIL:$1"; exit 1; }

# 1. Versión Debian
DEBIAN_VER=$(cat /etc/debian_version 2>/dev/null | grep -oE '^[0-9]+' || echo "0")
step 1 "Detectado Debian $DEBIAN_VER"
case $DEBIAN_VER in
    8) COD=jessie;  REPO_NAME="stable-raspbianjessie" ;;
    9) COD=stretch; REPO_NAME="stable-raspbianstretch" ;;
    *) fail "Version no soportada: Debian $DEBIAN_VER" ;;
esac

# 2. Espacio (mínimo 500MB; mono-runtime es liviano)
SPACE=$(df / | tail -1 | awk '{print $4}')
[ "$SPACE" -lt 500000 ] && fail "Espacio insuficiente: ${SPACE}KB"
step 2 "Espacio OK: ${SPACE}KB"

# 3. 🔍 DETECCIÓN DE FIREWALL / SALIDA BLOQUEADA (prueba los hosts reales)
step 3 "Verificando salida a internet (firewall de TI)..."
NET_OK=0
timeout 8 bash -c 'echo > /dev/tcp/archive.debian.org/80'        2>/dev/null && NET_OK=1
timeout 8 bash -c 'echo > /dev/tcp/download.mono-project.com/443' 2>/dev/null && NET_OK=1
timeout 8 bash -c 'echo > /dev/tcp/keyserver.ubuntu.com/80'      2>/dev/null && NET_OK=1
if [ "$NET_OK" -eq 0 ]; then
    fail "SALIDA_BLOQUEADA: el firewall del cliente no deja salir a internet. No se puede instalar Mono sin red (escalar a TI del cliente o instalar offline)."
fi
step 3 "Salida a internet OK"

# 4. 🔑 REPOS BASE (archive.debian.org para 8 y 9 en 2026) + Check-Valid-Until
step 4 "Corrigiendo repositorios base (archive.debian.org)"
dsudo cp /etc/apt/sources.list /etc/apt/sources.list.bak.$(date +%Y%m%d%H%M%S) 2>/dev/null || true
cat > /tmp/sources.list <<REPOEOF
deb http://archive.debian.org/debian ${COD} main contrib non-free
deb http://archive.debian.org/debian-security ${COD}/updates main contrib non-free
REPOEOF
dsudo cp /tmp/sources.list /etc/apt/sources.list
echo 'Acquire::Check-Valid-Until "false";' > /tmp/99-no-check-valid-until
dsudo cp /tmp/99-no-check-valid-until /etc/apt/apt.conf.d/99-no-check-valid-until
dsudo rm -rf /var/lib/apt/lists/* 2>/dev/null || true

# 5. Recuperar paquetes rotos
step 5 "Recuperando paquetes pendientes"
dsudo dpkg --configure -a || true
dsudo apt-get install -f -y || true

# 6. Dependencias (si dirmngr ya está, este paso es rápido)
step 6 "Asegurando dirmngr y dependencias"
dsudo apt-get install -y -o Acquire::Retries=5 dirmngr apt-transport-https ca-certificates gnupg \
    || fail "Fallo instalando dirmngr (repos base?)"

# 7. Clave GPG del repo Mono (con reintentos)
step 7 "Agregando clave GPG de Mono"
KEY_OK=0
for i in 1 2 3 4 5; do
    if dsudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 \
        --recv-keys 3FA7E0328081BFF6A14DA29AA6A19B38D3D831EF; then KEY_OK=1; break; fi
    sleep 3
done
[ "$KEY_OK" -eq 1 ] || fail "Fallo agregando clave GPG (firewall en puerto 80?)"

# 8. Repo Mono + PINNING (fuerza a usar download.mono-project.com, igual que el v3)
step 8 "Configurando repo Mono + pinning ($REPO_NAME)"
dsudo rm -f /etc/apt/sources.list.d/mono-*.list 2>/dev/null || true
echo "deb https://download.mono-project.com/repo/debian ${REPO_NAME} main" > /tmp/mono.list
dsudo cp /tmp/mono.list /etc/apt/sources.list.d/mono-official.list
cat > /tmp/mono-pin <<'PINEOF'
Package: mono-runtime libmono-* cli-common
Pin: origin download.mono-project.com
Pin-Priority: 1001
Package: *
Pin: origin download.mono-project.com
Pin-Priority: 900
PINEOF
dsudo cp /tmp/mono-pin /etc/apt/preferences.d/mono-pin

# 9. apt update
step 9 "Actualizando listas (apt update)"
dsudo apt-get update -o Acquire::Retries=5 -o Acquire::http::Timeout=60 || fail "Fallo en apt update"

# 10. Remover Mono viejo (igual que el v3)
step 10 "Removiendo Mono antiguo si existe"
dsudo apt-get remove -y mono-runtime libmono-* 2>/dev/null || true

# 11. Instalar mono-runtime (LIVIANO, no mono-complete) + lib web
step 11 "Instalando mono-runtime (liviano)"
dsudo apt-get install -y -t "$REPO_NAME" -o Acquire::Retries=5 -o Acquire::http::Timeout=120 \
    -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" \
    mono-runtime || fail "Fallo instalando mono-runtime"
dsudo apt-get install -y -t "$REPO_NAME" libmono-system-web4.0-cil 2>/dev/null || true

# 12. Verificar versión >= 6
step 12 "Verificando version de Mono"
MONO_VER=$(mono --version 2>/dev/null | head -1)
[ -z "$MONO_VER" ] && fail "Mono no se instalo"
MONO_NUM=$(echo "$MONO_VER" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "0.0.0")
MONO_MAJOR=$(echo "$MONO_NUM" | cut -d. -f1)
[ "$MONO_MAJOR" -lt 6 ] 2>/dev/null && fail "Version insuficiente: $MONO_NUM (necesita 6+)"
echo "DONE:SUCCESS:$MONO_NUM"
exit 0