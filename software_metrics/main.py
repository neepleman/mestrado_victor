import threading
import queue
import time
import subprocess
from datetime import datetime
import os
import psutil

# Imports dos nossos módulos
from src.ui.app_window import MKSApp
from src.hardware import CanHardwareManager
from src.data_logger import DataLogger
from src.j1939_core import J1939Parser

# Configuração para Raspberry Pi
os.environ['TK_SILENCE_DEPRECATION'] = '1'

class MainSystem:
    def __init__(self):
        # 1. Inicializa Subsistemas (Menos a UI completa)
        self.hardware = CanHardwareManager(channel='can0')
        self.logger = DataLogger(log_folder="logs")
        self.parser = J1939Parser("src/dados/pgn_config.csv")
        
        self.queue_ui = queue.Queue()
        self.running = True
        self.ui_skip_counter = 0
        self.monitor_thread = None
        
        # Variáveis de Estatística
        self.stat_rx_total = 0
        self.stat_dec_total = 0
        self.stat_last_rx_count = 0
        self.stat_time_last_calc = 0
        self.stat_latest_rx_interval = 0.0
        self.stat_latest_dec_time = 0.0

        # 2. Inicializa a App, passando a função de configuração como Callback
        # Isso diz: "Quando terminar o Splash, chame self.on_gui_ready"
        self.app = MKSApp(on_ready_callback=self.on_gui_ready)

    def on_gui_ready(self):
        """Esta função só roda quando a Interface Principal nascer."""
        print("[MAIN] Interface Gráfica carregada. Vinculando botões...")
        
        # Agora é seguro acessar main_frame
        ui = self.app.main_frame
        
        # Injeta os comandos nos botões
        ui.btn_connect.configure(command=self.on_connect_click)
        ui.btn_test_frame.configure(command=self.on_send_test)
        
        # Inicia o loop de atualização da UI
        self.process_ui_queue()

    def on_connect_click(self):
        ui = self.app.main_frame
        
        if not ui.is_connected:
            # --- CONECTAR ---
            bitrate = int(ui.combo_bitrate.get())
            interface = ui.combo_interface.get()
            self.hardware.channel = interface
            
            is_silent = (ui.switch_silent.get() == 1)
            is_loopback = (ui.switch_loop.get() == 1)

            print(f"[MAIN] Solicitando conexão: {interface} @ {bitrate}bps")
            
            # Chama a função limpa do hardware, passando todos os parâmetros
            if self.hardware.conectar(bitrate, force_ack=not is_silent, is_loopback=is_loopback):
                self.logger.start_new_session()
                ui.toggle_connection() 
                self.start_monitoring()
            else:
                print("[MAIN] Falha ao configurar a interface de hardware!")
        
        else:
            # --- DESCONECTAR ---
            self.stop_monitoring()
            self.hardware.desconectar()
            self.logger.stop()
            ui.toggle_connection()

    def on_send_test(self):
        # A interface repassa o pedido para o hardware, sem rodar "os.system"
        if self.hardware.enviar_mensagem("123", "DEADBEEF"):
            print("[MAIN] Frame teste enviado com sucesso.")
        else:
            print("[MAIN] Falha ao enviar frame teste.")

    def start_monitoring(self):
        self.running = True
        self.stat_time_last_calc = time.perf_counter() # Reseta o relógio
        
        self.monitor_thread = threading.Thread(target=self._thread_can_reader, daemon=True)
        self.monitor_thread.start()
        
        # --- INICIA A COLETA DE MÉTRICAS PARA O ARTIGO ---
        self.metrics_thread = threading.Thread(target=self._thread_metrics_logger, daemon=True)
        self.metrics_thread.start()
        # -------------------------------------------------
        
        self.update_stats_ui() # Inicia o loop de estatísticas

    def stop_monitoring(self):
        self.running = False

    def _thread_metrics_logger(self):
        """Espião silencioso que grava as métricas C e D para o Artigo Científico"""
        arquivo_metricas = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "dados", "metricas_artigo.csv")
        
        # Cria o cabeçalho do CSV se o arquivo não existir
        if not os.path.exists(arquivo_metricas):
            with open(arquivo_metricas, "w", newline="") as f:
                f.write("Timestamp,CPU_Percent,RAM_MB,Fila_UI,Tempo_Decod_ms,Total_Rx,Erros_Parse\n")
            
        print("[MÉTRICAS] Gravador de Performance iniciado.")

        # Loop de amostragem a cada 1 segundo
        while self.running:
            try:
                cpu = psutil.cpu_percent(interval=1.0)
                # Pega a memória usada do sistema em Megabytes
                ram = psutil.virtual_memory().used / (1024 * 1024) 
                fila = self.queue_ui.qsize()
                
                # A latência média da última decodificação
                t_decod = self.stat_latest_dec_time 
                
                # Teste D: FMEA Prático (Quantas msgs não viraram dados úteis)
                erros = self.stat_rx_total - self.stat_dec_total
                
                agora = datetime.now().strftime('%H:%M:%S')

                with open(arquivo_metricas, "a", newline="") as f:
                    f.write(f"{agora},{cpu},{ram:.1f},{fila},{t_decod:.4f},{self.stat_rx_total},{erros}\n")
            except Exception as e:
                pass # Evita que a thread de métricas crashe o sistema
    
    def _thread_can_reader(self):
        cmd = ['sudo', 'candump', self.hardware.channel]
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, bufsize=1)
            print("[THREAD] Leitura iniciada.")
            
            while self.running:
                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None: break
                    continue

                timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                line = line.strip()
                
                parts = line.split()
                if len(parts) > 3:
                    try:
                        can_id_hex = parts[1]
                        dlc = parts[2].strip('[]')
                        data_hex = ''.join(parts[3:]).upper()
                        
                        self.logger.log_raw(timestamp, can_id_hex, dlc, data_hex)
                        
                        # --- INÍCIO DA COLETA DE ESTATÍSTICA ---
                        self.stat_rx_total += 1
                        
                        can_id = int(can_id_hex, 16)
                        
                        t_dec_start = time.perf_counter()
                        result = self.parser.decodificar_mensagem(can_id_hex, data_hex)
                        t_dec_end = time.perf_counter()
                        
                        self.stat_latest_dec_time = (t_dec_end - t_dec_start) * 1000 # Converte para ms
                        
                        if result:
                            self.stat_dec_total += 1
                            for res in result: 
                                # Agora pegamos as chaves corretas do seu j1939_core.py
                                spn_str = str(res.get('spn', ''))
                                label = res.get('sp_label', 'Desconhecido')
                                valor = res.get('valor', 'UD')
                                unidade = res.get('unidade', '')
                                
                                self.logger.log_decoded(timestamp, label, valor, unidade)
                                self.queue_ui.put(res)

                    except Exception as e:
                        pass # Erro de parse pontual

            process.terminate()
            try:
                process.wait(timeout=1)
            except:
                subprocess.run(f"sudo killall candump", shell=True)
        except Exception as e:
            print(f"Erro ao iniciar candump: {e}")
        print("[THREAD] Leitura finalizada.")

    def update_stats_ui(self):
        """Atualiza o painel de métricas a cada 500ms sem travar a interface principal."""
        if self.running and hasattr(self.app, 'main_frame'):
            now = time.perf_counter()
            dt = now - self.stat_time_last_calc
            
            # Evita divisão por zero e calcula mensagens por segundo (Throughput)
            if dt > 0:
                tps = (self.stat_rx_total - self.stat_last_rx_count) / dt
                # Calcula o tempo médio entre chegadas (Intervalo Rx)
                self.stat_latest_rx_interval = (1000 / tps) if tps > 0 else 0.0
            else:
                tps = 0
                
            self.stat_time_last_calc = now
            self.stat_last_rx_count = self.stat_rx_total

            # Calcula a taxa de aproveitamento do Parser
            perc = (self.stat_dec_total / self.stat_rx_total * 100) if self.stat_rx_total > 0 else 0.0

            # Atualiza os componentes da interface com textos curtos
            ui = self.app.main_frame
            ui.lbl_stat_rx.configure(text=f"Rx: {self.stat_rx_total}")
            ui.lbl_stat_dec.configure(text=f"Decod: {self.stat_dec_total}")
            ui.lbl_stat_perc.configure(text=f"Sucesso: {perc:.1f}%")
            ui.lbl_stat_tps.configure(text=f"Taxa: {int(tps)} msg/s")
            ui.lbl_stat_time_rx.configure(text=f"Int. Rx: {self.stat_latest_rx_interval:.2f} ms")
            ui.lbl_stat_time_dec.configure(text=f"T. Decod: {self.stat_latest_dec_time:.4f} ms")

        # Se o sistema estiver rodando, agenda a próxima atualização
        if self.running:
            self.app.after(500, self.update_stats_ui)

    def process_ui_queue(self):
        try:
            # --- ATUALIZAÇÃO DO INDICADOR DE FILA ---
            if hasattr(self.app, 'main_frame'):
                tamanho_fila = self.queue_ui.qsize()
                self.app.main_frame.lbl_queue_status.configure(text=f"Fila (Queue): {tamanho_fila} msgs")
                
                # Opcional: Mudar a cor se a fila estiver muito grande (indicando gargalo)
                if tamanho_fila > 50:
                    self.app.main_frame.lbl_queue_status.configure(text_color="red")
                else:
                    self.app.main_frame.lbl_queue_status.configure(text_color="gray")
            # ----------------------------------------           
            
            
            while not self.queue_ui.empty():
                item = self.queue_ui.get_nowait()
                self.ui_skip_counter += 1
                
                # A mágica da subamostragem visual: Só desenha o texto a cada 15 mensagens processadas
                should_draw_text = (self.ui_skip_counter % 15 == 0)

                if 'raw' in item:
                    if should_draw_text and hasattr(self.app, 'main_frame'):
                        self.app.main_frame.txt_raw.insert("0.0", item['raw'] + "\n")
                        if int(self.app.main_frame.txt_raw.index('end-1c').split('.')[0]) > 20:
                             self.app.main_frame.txt_raw.delete('21.0', 'end')
                
                else:
                    if should_draw_text and hasattr(self.app, 'main_frame'):
                        # Atualiza os textos usando as novas chaves
                        msg = f"{item.get('sp_label', '')}: {item.get('valor', '')} {item.get('unidade', '')}"
                        self.app.main_frame.txt_decod.insert("0.0", msg + "\n")
                        if int(self.app.main_frame.txt_decod.index('end-1c').split('.')[0]) > 20:
                             self.app.main_frame.txt_decod.delete('21.0', 'end')
                        
                    # --- O NOVO ROTEADOR POR SPN ---
                    # Avalia TODAS as mensagens na velocidade da luz para mexer a agulha/LED
                    if hasattr(self.app, 'main_frame'):
                        spn_str = str(item.get('spn', ''))
                        valor = item.get('valor', 'UD')
                        
                        # Se o SPN estiver desenhado na tela, atualiza o valor dele!
                        if spn_str in self.app.main_frame.componentes_visuais:
                            self.app.main_frame.componentes_visuais[spn_str].set_value(valor)

        except queue.Empty:
            pass
        finally:
            self.app.after(50, self.process_ui_queue)

    def run(self):
        def on_close():
            print("Encerrando sistema...")
            self.stop_monitoring()
            self.hardware.desconectar()
            self.app.destroy()
            
        self.app.protocol("WM_DELETE_WINDOW", on_close)
        self.app.mainloop()

if __name__ == "__main__":
    system = MainSystem()
    system.run()
