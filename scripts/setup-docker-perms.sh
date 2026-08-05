#!/usr/bin/env bash
# make me docker admin - ejecutalo con tu usuario normal
set -euo pipefail

# 1. Grupo docker (lo crea si no existe)
if ! getent group docker >/dev/null; then
    sudo groupadd docker
fi

# 2. Sumar tu usuario al grupo docker
sudo usermod -aG docker "$USER"

# 3. Propietario del socket (por si Docker ya estaba corriendo)
sudo chown root:docker /var/run/docker.sock
sudo chmod 660 /var/run/docker.sock

# 4. Activar sin reloguear (sólo para esta shell)
newgrp docker <<'EOF'
docker info >/dev/null && echo "✅ Docker OK en esta shell"
EOF

echo "➡️  Cierra sesión y vuelve a entrar para que el grupo quede permanente."
echo "    Después: 'docker compose restart app' debería funcionar sin sudo."
