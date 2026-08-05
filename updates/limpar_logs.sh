#!/bin/bash

# Limpa os arquivos mono_crash que ficam na raiz e podem consumir o SD todo.
sudo find / -maxdepth 1 -name "mono_crash*" -type f -delete

# Limpa os arquivos de log das pastas abaixo e suas sub-pastas
DIRETORIOS=(
    "/home/solinfnet/LogGeral"
    "/home/solinfnet/LogSerial"
    "/home/solinfnet/GeneralLog"
    "/home/solinfnet/Pluviometros/LogGeral"
    "/home/solinfnet/Pluviometros/LogSerial"
    "/home/solinfnet/Meteorologia/LogGeral"
    "/home/solinfnet/Meteorologia/LogSerial"
)

for DIR in "${DIRETORIOS[@]}"; do
    if [ -d "$DIR" ]; then
        find "$DIR" -type f -mtime +60 -delete
    fi
done