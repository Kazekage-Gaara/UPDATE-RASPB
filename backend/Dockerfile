FROM python:3.11-slim

# Instalar herramientas de red y sshpass
RUN apt-get update && apt-get install -y \
    openssh-client \
    sshpass \
    iputils-ping \
    rsync \
    && rm -rf /var/lib/apt/lists/*

# ⭐️ SOLUCIÓN MÁGICA: Configurar SSH globalmente en el contenedor
# Esto evita el prompt "yes/no" sin necesidad de usar "-o" en la línea de comandos
RUN echo "Host *" >> /etc/ssh/ssh_config && \
    echo "    StrictHostKeyChecking no" >> /etc/ssh/ssh_config && \
    echo "    UserKnownHostsFile /dev/null" >> /etc/ssh/ssh_config && \
    echo "    LogLevel ERROR" >> /etc/ssh/ssh_config

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# C-4: --reload eliminado en producción para evitar reinicio del worker y pérdida de progreso.
# En desarrollo usar override de docker-compose o un Dockerfile.dev con --reload.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
