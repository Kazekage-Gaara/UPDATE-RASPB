#!/bin/bash

function percorrer_diretorio() {
    local diretorio="$1"
    for arquivo in "$diretorio"/*; do
        if [ -d "$arquivo" ]; then
            percorrer_diretorio "$arquivo"
        elif [ -r "$arquivo" ]; then
            if ! grep -q '[[:print:]]' "$arquivo"; then
                rm "$arquivo"
                echo "Arquivo $arquivo excluído por conter apenas caracteres não imprimíveis."
            else
                sed -i 's/[^[:print:]]//g' "$arquivo"
                echo "Arquivo $arquivo editado com sucesso."
            fi
        else
            echo "Não é possível ler o arquivo $arquivo."
        fi
    done
}

diretorio="/home/solinfnet/TempDB"

percorrer_diretorio "$diretorio"
