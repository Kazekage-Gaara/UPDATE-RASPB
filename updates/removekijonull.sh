#!/bin/bash
# Remove bytes no imprimibles de archivos de datos sin recorrer rutas inexistentes.
set -u

BASE_DIR="${SOLINFNET_HOME:-/home/solinfnet}"

percorrer_diretorio() {
    local diretorio="$1"
    [ -d "$diretorio" ] || return 0

    while IFS= read -r -d '' arquivo; do
        if ! grep -q '[[:print:]]' "$arquivo"; then
            rm -- "$arquivo"
            echo "Arquivo $arquivo excluido por conter apenas caracteres nao imprimiveis."
        elif sed -i 's/[^[:print:]]//g' "$arquivo"; then
            echo "Arquivo $arquivo editado com sucesso."
        else
            echo "Nao foi possivel editar o arquivo $arquivo." >&2
        fi
    done < <(find "$diretorio" -type f -readable -print0)
}

percorrer_diretorio "$BASE_DIR/TempDB"
percorrer_diretorio "$BASE_DIR/Meteorologia"
