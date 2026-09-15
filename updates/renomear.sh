#!/bin/bash
# Convierte paquetes temporales pendientes en los directorios de datos activos.
set -u

BASE_DIR="${SOLINFNET_HOME:-/home/solinfnet}"

renomear_pacotes() {
    local diretorio="$1"
    [ -d "$diretorio" ] || return 0

    while IFS= read -r -d '' arquivo; do
        destino="${arquivo%.ptemp}.Packet"
        if mv -- "$arquivo" "$destino"; then
            echo "Pacote renomeado: $arquivo -> $destino"
        else
            echo "Falha ao renomear: $arquivo" >&2
        fi
    done < <(find "$diretorio" -type f -name '*.ptemp' -print0)
}

renomear_pacotes "$BASE_DIR/TempDB"
renomear_pacotes "$BASE_DIR/Meteorologia"
