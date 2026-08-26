import subprocess
import os
import socket

PASSWORD = os.getenv("RASP_PASSWORD", "")
USER = os.getenv("SSH_USER", "solinfnet")

def run_ssh_command(ip: str, cmd: str, timeout: int = 15, port: int | None = None) -> dict:
    """
    Ejecuta comando SSH respetando restricción: SOLO ssh user@ip "cmd"
    """
    if not PASSWORD:
        return {"success": False, "error": "RASP_PASSWORD vacía en .env"}

    # Comando limpio, sin opciones -o
    full_cmd = ["sshpass", "-p", PASSWORD, "ssh"]
    if port:
        full_cmd.extend(["-p", str(port)])
    full_cmd.extend([f"{USER}@{ip}", cmd])
    
    try:
        result = subprocess.run(
            full_cmd, 
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        if result.returncode == 0:
            return {"success": True, "output": result.stdout.strip()}
        else:
            # Capturamos el código de error para depurar
            err_msg = result.stderr.strip() or result.stdout.strip() or "Sin mensaje"
            return {"success": False, "error": f"Código {result.returncode} | {err_msg}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout SSH (15s)"}
    except Exception as e:
        return {"success": False, "error": f"Excepción: {str(e)}"}

def ping_host(ip: str, port: int | None = None) -> bool:
    try:
        if port:
            with socket.create_connection((ip, port), timeout=2):
                return True
        result = subprocess.run(["ping", "-c", "1", "-W", "2", ip], capture_output=True)
        return result.returncode == 0
    except:
        return False
