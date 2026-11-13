import subprocess
import time

class CanHardwareManager:
    def __init__(self, channel='can0'):
        self.channel = channel
        self.current_bitrate = 500000
        self.listen_only_mode = True  
        self.is_connected = False

    def _exec_cmd(self, cmd_string):
        """Executa comandos do sistema com sudo e timeout"""
        try:
            full_cmd = f"sudo {cmd_string}"
            subprocess.run(full_cmd, shell=True, check=True, timeout=5)
            return True
        except subprocess.CalledProcessError as e:
            print(f"[HW Error] Comando falhou: {cmd_string} -> {e}")
            return False
        except subprocess.TimeoutExpired:
            print(f"[HW Error] Timeout: {cmd_string}")
            return False

    def conectar(self, bitrate, force_ack=False, is_loopback=False):
        """
        Configura e levanta a interface CAN.
        force_ack: Se False (padrão), ativa 'listen-only on'.
        is_loopback: Se True, ativa o 'loopback on' (para testes de bancada/software).
        """
        self.desconectar() 
        
        self.current_bitrate = bitrate
        
        # Lógica de Segurança Crítica (Escuta vs Fala)
        if force_ack:
            self.listen_only_mode = False
            mode_str = "listen-only off"
        else:
            self.listen_only_mode = True
            mode_str = "listen-only on" 

        # Lógica de Teste de Bancada (Loopback)
        loop_str = "loopback on" if is_loopback else ""

        print(f"[HW] Configurando {self.channel}: {bitrate}bps | Mudo: {self.listen_only_mode} | Loop: {is_loopback}")

        # Sequência de comandos ip link compilada em um só passo para o tipo
        steps = [
            f"ip link set {self.channel} down",
            f"ip link set {self.channel} type can bitrate {bitrate} {mode_str} {loop_str}",
            f"ip link set {self.channel} up",
            f"ifconfig {self.channel} txqueuelen 1000"
        ]

        for cmd in steps:
            if not self._exec_cmd(cmd):
                return False
        
        self.is_connected = True
        return True

    def desconectar(self):
        """Derruba a interface com segurança."""
        self._exec_cmd(f"ip link set {self.channel} down")
        self.is_connected = False

    def enviar_mensagem(self, can_id_hex, data_hex):
        """Envia um frame para a rede usando o cansend do Linux."""
        if not self.is_connected:
            print(f"[HW] Erro: Tentativa de envio com interface {self.channel} offline.")
            return False
            
        if self.listen_only_mode:
            print(f"[HW] Erro: Interface {self.channel} está em modo Listen-Only. Envio bloqueado por segurança.")
            return False

        cmd = f"cansend {self.channel} {can_id_hex}#{data_hex}"
        return self._exec_cmd(cmd)

    def auto_diagnostico(self):
        print("[HW] Iniciando Auto-Diagnóstico...")
        pass
