import threading
import queue
import time
import subprocess
from datetime import datetime
import os

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
        
        # ---------------------------------------------------------
        # ATUALIZAÇÃO PARA O MESTRADO: Fila com Limite (Prevenção OOM)
        # ---------------------------------------------------------
        self.queue_ui = queue.Queue(maxsize=5000) 
        
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
        
        # Variável para rastrear a política de descarte
        self.stat_dropped_ui_messages = 0 

        # 2. Inicializa a App, passando a função de configuração como Callback
        self.app = MKSApp(on_ready_callback=self.on_gui_ready)

    def on_gui_ready(self):
        """Esta função só roda quando a Interface Principal nascer."""
        print("[MAIN] Interface Gráfica carregada. Vinculando botões...")
        
        ui = self.app.main_frame
        
        ui.btn_connect.configure(command=self.on_connect_click)
        ui.btn_test_frame.configure(command=self.on_send_test)
        
        self.process_ui_queue()

    def on_connect_click(self):
        ui = self.app.main_frame
        
        if not ui.is_connected:
            bitrate = int(ui.combo_bitrate.get())
            interface = ui.combo_interface.get()
            self.hardware.channel = interface
            
            is_silent = (ui.switch_silent.get() == 1)
            is_loopback = (ui.switch_loop.get() == 1)

            print(f"[MAIN] Solicitando conexão: {interface} @ {bitrate}bps")
            
            if self.hardware.conectar(bitrate, force_ack=not is_silent, is_loopback=is_loopback):
                self.logger.start_new_session()
                ui.toggle_connection() 
                self.start_monitoring()
            else:
                print("[MAIN] Falha ao configurar a interface de hardware!")
        
        else:
            self.stop_monitoring()
            self.hardware.desconectar()
            self.logger.stop()
            ui.toggle_connection()

    def on_send_test(self):
        if self.hardware.enviar_mensagem("123", "DEADBEEF"):
            print("[MAIN] Frame teste enviado com sucesso.")
        else:
            print("[MAIN] Falha ao enviar frame teste.")

    def start_monitoring(self):
        self.running = True
        self.stat_time_last_calc = time.perf_counter()
        self.monitor_thread = threading.Thread(target=self._thread_can_reader, daemon=True)
        self.monitor_thread.start()
        self.update_stats_ui()

    def stop_monitoring(self):
        self.running = False
        
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
                        
                        # LOG BRUTO (Alta Prioridade)
                        self.logger.log_raw(timestamp, can_id_hex, dlc, data_hex)
                        
                        self.stat_rx_total += 1
                        can_id = int(can_id_hex, 16)
                        
                        t_dec_start = time.perf_counter()
                        result = self.parser.decodificar_mensagem(can_id_hex, data_hex)
                        t_dec_end = time.perf_counter()
                        
                        self.stat_latest_dec_time = (t_dec_end - t_dec_start) * 1000 
                        
                        if result:
                            self.stat_dec_total += 1
                            for res in result: 
                                spn_str = str(res.get('spn', ''))
                                label = res.get('sp_label', 'Desconhecido')
                                valor = res.get('valor', 'UD')
                                unidade = res.get('unidade', '')
                                
                                # LOG DECODIFICADO (Média Prioridade)
                                self.logger.log_decoded(timestamp, label, valor, unidade)
                                
                                # ---------------------------------------------------------
                                # ATUALIZAÇÃO PARA O MESTRADO: Política de Descarte da UI
                                # ---------------------------------------------------------
                                try:
                                    self.queue_ui.put(res, block=False)
                                except queue.Full:
                                    # Política Drop Newest: Fila cheia, descarta atualização visual
                                    self.stat_dropped_ui_messages += 1

                    except Exception as e:
                        pass 

            process.terminate()
            try:
                process.wait(timeout=1)
            except:
                subprocess.run(f"sudo killall candump", shell=True)
        except Exception as e:
            print(f"Erro ao iniciar candump: {e}")
        print("[THREAD] Leitura finalizada.")

    def update_stats_ui(self):
        if self.running and hasattr(self.app, 'main_frame'):
            now = time.perf_counter()
            dt = now - self.stat_time_last_calc
            
            if dt > 0:
                tps = (self.stat_rx_total - self.stat_last_rx_count) / dt
                self.stat_latest_rx_interval = (1000 / tps) if tps > 0 else 0.0
            else:
                tps = 0
                
            self.stat_time_last_calc = now
            self.stat_last_rx_count = self.stat_rx_total

            perc = (self.stat_dec_total / self.stat_rx_total * 100) if self.stat_rx_total > 0 else 0.0

            ui = self.app.main_frame
            ui.lbl_stat_rx.configure(text=f"Rx: {self.stat_rx_total}")
            ui.lbl_stat_dec.configure(text=f"Decod: {self.stat_dec_total}")
            ui.lbl_stat_perc.configure(text=f"Sucesso: {perc:.1f}%")
            ui.lbl_stat_tps.configure(text=f"Taxa: {int(tps)} msg/s")
            ui.lbl_stat_time_rx.configure(text=f"Int. Rx: {self.stat_latest_rx_interval:.2f} ms")
            ui.lbl_stat_time_dec.configure(text=f"T. Decod: {self.stat_latest_dec_time:.4f} ms")

        if self.running:
            self.app.after(500, self.update_stats_ui)

    def process_ui_queue(self):
        try:
            if hasattr(self.app, 'main_frame'):
                tamanho_fila = self.queue_ui.qsize()
                # Mostra também as mensagens descartadas pela UI
                self.app.main_frame.lbl_queue_status.configure(
                    text=f"Fila: {tamanho_fila} | Drops UI: {self.stat_dropped_ui_messages}"
                )
                
                if tamanho_fila > (self.queue_ui.maxsize * 0.8): # Fica vermelho se passar de 80% do limite
                    self.app.main_frame.lbl_queue_status.configure(text_color="red")
                else:
                    self.app.main_frame.lbl_queue_status.configure(text_color="gray")
            
            while not self.queue_ui.empty():
                item = self.queue_ui.get_nowait()
                self.ui_skip_counter += 1
                
                should_draw_text = (self.ui_skip_counter % 15 == 0)

                if 'raw' in item:
                    if should_draw_text and hasattr(self.app, 'main_frame'):
                        self.app.main_frame.txt_raw.insert("0.0", item['raw'] + "\n")
                        if int(self.app.main_frame.txt_raw.index('end-1c').split('.')[0]) > 20:
                             self.app.main_frame.txt_raw.delete('21.0', 'end')
                
                else:
                    if should_draw_text and hasattr(self.app, 'main_frame'):
                        msg = f"{item.get('sp_label', '')}: {item.get('valor', '')} {item.get('unidade', '')}"
                        self.app.main_frame.txt_decod.insert("0.0", msg + "\n")
                        if int(self.app.main_frame.txt_decod.index('end-1c').split('.')[0]) > 20:
                             self.app.main_frame.txt_decod.delete('21.0', 'end')
                        
                    if hasattr(self.app, 'main_frame'):
                        spn_str = str(item.get('spn', ''))
                        valor = item.get('valor', 'UD')
                        
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