#!/bin/bash

# Define o arquivo onde será salvo o LOG
LOG_FILE="/home/solinfnet/check_webpage.log"

# Verifica se existe o arquivo para registrar log, senão cria ele e dá permissão para escrita.
if [ ! -e "$LOG_FILE" ]; then
    touch "$LOG_FILE" && chmod 777 "$LOG_FILE"
    sleep 2
    echo "#LOG DO MONITORAMENTO WEB SOLINFNET" >> "$LOG_FILE"
fi

# Variável de verificação de falso-positivo para KIJO ACK INDEX
ack_check_count=0

# Loop principal para monitoramento da página web
while true; do
    curl --silent --head --fail "http://admin:admin@localhost:8085" --max-time 5 >/dev/null
    if [ ! $? -eq 52 ]; then # verifica se a saída da instrução NÃO retorna página encontrada
        systemctl restart solinfnet # caso não encontre página, reinicia apeans o serviço SolinfNet
        echo "$(date +'%d/%m/%Y %H:%M:%S'): Serviço SolinfNet fora de execução" >> "$LOG_FILE" # grava no log a data/hora com o erro
    else
        # Obtém o timestamp da data atual do Google
        data_timestamp=$(date -d "$(wget --method=HEAD -qSO- --max-redirect=0 google.com 2>&1 | sed -n 's/^ *Date: *//p')" +"%s")

        # Obtém o conteúdo do JS da página
        conteudo_web=$(curl -sS "http://admin:admin@localhost:8085/0.outlog?_=$data_timestamp")

        # Verifica se o KIJO de monitoramento do gateway (KIJO77,00) contém o valor "Erro ao Guardar Pacote" na comunicação de saída e reinicia o equipamento 
        if echo "$conteudo_web" | grep -q ",00000008,"; then
            systemctl stop solinfnet # para a SolinfNet para evitar coleta quebrada e perda de informação
            sleep 30 # aguarda 30s para executar a ação
            echo "$(date +'%d/%m/%Y %H:%M:%S'): Erro ao guardar pacote identificado" >> "$LOG_FILE" # grava no log a data/hora com o erro
            sudo reboot # reinicia o SO
        fi
        
        # Verifica se está recebendo confirmação dos pacotes enviadas ao SNS na comuniação de saída
        if echo "$conteudo_web" | grep -q "Kijos ACK Index"; then 
            ack_check_count=0 # caso encontre confirmação, zera a variável
        else
            ((ack_check_count++)) # caso não encontre, adiciona +1 ao valor da variável
            if [ $ack_check_count -ge 2 ]; then # faz a verificação duas vezes para não correr o risco de ter limpado a saída (old data removed)
                systemctl stop solinfnet # para a SolinfNet para evitar coleta quebrada e perda de informação
                sleep 30 # aguarda 30s para executar a ação
                echo "$(date +'%d/%m/%Y %H:%M:%S'): Não recebendo KIJO ACK INDEX OK" >> "$LOG_FILE" # grava no log a data/hora com o erro
                sudo reboot # reinicia o SO
            fi
        fi
    fi
    sleep 60  # Tempo de 60s antes de voltar o loop
done
