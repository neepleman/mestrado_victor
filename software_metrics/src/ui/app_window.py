import customtkinter as ctk
from PIL import Image
import time
import threading
import os
import random
import json
from src.ui.status_leds import StatusLEDArray

# Tenta importar os Gauges. 
# Se você salvou gauges.py na mesma pasta ui/, o import abaixo funciona se rodar do main.
# Se der erro, verifique se existe um arquivo vazio __init__.py na pasta ui.
try:
    from src.ui.gauges import ModernGauge
except ImportError:
    # Fallback caso rode o arquivo isolado para teste
    from gauges import ModernGauge

# --- Configuração do Tema ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class SplashScreenFrame(ctk.CTkFrame):
    """(Código da Splash Screen mantido igual)"""
    def __init__(self, master, on_finish_callback):
        super().__init__(master)
        self.on_finish_callback = on_finish_callback
        self.pack(fill="both", expand=True)
        self.configure(fg_color="#1a1a1a")

        logo_path = os.path.join("assets", "logo.png")
        try:
            pil_image = Image.open(logo_path)
            self.logo_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(300, 300))
            self.lbl_logo = ctk.CTkLabel(self, image=self.logo_image, text="")
        except FileNotFoundError:
            self.lbl_logo = ctk.CTkLabel(self, text="MKS MASTER SYSTEM\n(Protótipo Mestrado)", 
                                         font=ctk.CTkFont(size=30, weight="bold"))
        
        self.lbl_logo.pack(pady=(100, 30), expand=True)
        self.lbl_status = ctk.CTkLabel(self, text="Carregando módulos...", font=ctk.CTkFont(size=14))
        self.lbl_status.pack(pady=(0, 10))
        self.progress_bar = ctk.CTkProgressBar(self, width=400, height=15)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(pady=(0, 100))
        
        threading.Thread(target=self.simulate_loading, daemon=True).start()

    def simulate_loading(self):
        steps = [(0.3, "Detectando Interface CAN..."), (0.6, "Carregando Gauges..."), (1.0, "Iniciando...")]
        for prog, text in steps:
            time.sleep(0.5)
            self.after(0, lambda p=prog, t=text: (self.progress_bar.set(p), self.lbl_status.configure(text=t)))
        time.sleep(0.5)
        self.after(0, self.finish_loading)

    def finish_loading(self):
        self.pack_forget()
        self.destroy()
        self.on_finish_callback()

class MainInterfaceFrame(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.pack(fill="both", expand=True)
        self.is_connected = False

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === SIDEBAR (Mantida Igual) ===
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(10, weight=1)

        lbl_title = ctk.CTkLabel(self.sidebar, text="Painel de Controle", font=ctk.CTkFont(size=18, weight="bold"))
        lbl_title.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.status_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.status_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        self.led_conn = ctk.CTkLabel(self.status_frame, text="  ", width=15, height=15, corner_radius=8, fg_color="red")
        self.led_conn.grid(row=0, column=0, padx=5)
        self.lbl_conn = ctk.CTkLabel(self.status_frame, text="Desconectado", font=ctk.CTkFont(size=12))
        self.lbl_conn.grid(row=0, column=1, sticky="w")

        self.led_ack = ctk.CTkLabel(self.status_frame, text="  ", width=15, height=15, corner_radius=8, fg_color="#00FF00")
        self.led_ack.grid(row=1, column=0, padx=5, pady=5)
        self.lbl_ack = ctk.CTkLabel(self.status_frame, text="Seguro (No ACK)", font=ctk.CTkFont(size=12))
        self.lbl_ack.grid(row=1, column=1, sticky="w")

        self.led_rec = ctk.CTkLabel(self.status_frame, text="REC ●", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray")
        self.led_rec.grid(row=2, column=1, sticky="w", pady=(5,0))

        ctk.CTkLabel(self.sidebar, text="Configuração Hardware", anchor="w", text_color="gray").grid(row=3, column=0, padx=20, pady=(10,0), sticky="ew")

        self.combo_interface = ctk.CTkComboBox(self.sidebar, values=["can0", "can1"])
        self.combo_interface.grid(row=4, column=0, padx=20, pady=5, sticky="ew")
        self.combo_interface.set("can0")

        self.combo_bitrate = ctk.CTkComboBox(self.sidebar, values=["250000", "500000", "1000000"])
        self.combo_bitrate.grid(row=5, column=0, padx=20, pady=5, sticky="ew")
        self.combo_bitrate.set("250000")

        ctk.CTkLabel(self.sidebar, text="Modos de Operação", anchor="w", text_color="gray").grid(row=6, column=0, padx=20, pady=(15,0), sticky="ew")

        self.switch_silent = ctk.CTkSwitch(self.sidebar, text="Modo Silencioso", command=self.toggle_silent_mode)
        self.switch_silent.grid(row=7, column=0, padx=20, pady=10, sticky="ew")
        self.switch_silent.select()

        self.switch_loop = ctk.CTkSwitch(self.sidebar, text="Loopback (Debug)")
        self.switch_loop.grid(row=8, column=0, padx=20, pady=5, sticky="ew")

        self.btn_connect = ctk.CTkButton(self.sidebar, text="CONECTAR CAN", height=50, 
                                         fg_color="#2e8b57", hover_color="#1e5b38",
                                         font=ctk.CTkFont(size=14, weight="bold"),
                                         command=self.toggle_connection)
        self.btn_connect.grid(row=9, column=0, padx=20, pady=(20, 10), sticky="ew")

        self.btn_test_frame = ctk.CTkButton(self.sidebar, text="Enviar Frame Teste", 
                                            fg_color="#444", hover_color="#333",
                                            state="disabled",
                                            command=self.send_test_frame)
        self.btn_test_frame.grid(row=10, column=0, padx=20, pady=(5, 5), sticky="ew")

        self.lbl_queue_status = ctk.CTkLabel(self.sidebar, text="Fila (Queue): 0 msgs", font=ctk.CTkFont(size=11), text_color="gray")
        self.lbl_queue_status.grid(row=11, column=0, pady=(5))

        # === MAIN CONTENT (Direita) ===
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_content.grid_rowconfigure(1, weight=0) # Gauges não esticam
        self.main_content.grid_rowconfigure(2, weight=0) # Estatísticas não esticam
        self.main_content.grid_rowconfigure(3, weight=1) # Logs esticam para preencher o resto
        #self.main_content.grid_columnconfigure(0, weight=1)

        # Header
        lbl_head = ctk.CTkLabel(self.main_content, text="Decoder Máquinas Agrícolas - Victor Augusto", font=ctk.CTkFont(size=22))
        lbl_head.grid(row=0, column=0, sticky="w", pady=(0, 10))

        # === ÁREA DOS MOSTRADORES DINÂMICOS ===
        self.visual_container = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.visual_container.grid(row=1, column=0, sticky="nsew", pady=(0, 20))
        
        self.leds_frame = ctk.CTkFrame(self.visual_container, fg_color="transparent")
        self.leds_frame.pack(side="top", fill="x", pady=(0, 10))
        
        self.gauges_frame = ctk.CTkFrame(self.visual_container, fg_color="transparent")
        self.gauges_frame.pack(side="top", fill="x")
        
        # Dicionário de Ouro: Guarda o componente pelo número do SPN
        self.componentes_visuais = {}
        self._carregar_config_json()

    def _carregar_config_json(self):
        try:
            with open("ui_config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"[UI] Aviso: Arquivo ui_config.json não encontrado ou inválido. Usando tela limpa. Erro: {e}")
            config = {"gauges": [], "leds": []}

        # 1. Constrói os LEDs no topo
        for idx, led_data in enumerate(config.get("leds", [])):
            spn = str(led_data["spn"])
            comp = StatusLEDArray(self.leds_frame, title=led_data["title"], max_val=led_data["max_val"], width=180, height=100)
            comp.grid(row=0, column=idx, padx=5)
            self.componentes_visuais[spn] = comp

        # 2. Constrói os Gauges embaixo
        # Cores aleatórias pré-definidas para dar contraste
        cores = ["#2ecc71", "#e67e22", "#f1c40f", "#e74c3c", "#9b59b6", "#3498db"]
        
        for idx, gauge_data in enumerate(config.get("gauges", [])):
            spn = str(gauge_data["spn"])
            cor = cores[idx % len(cores)]
            col = idx % 5 # Máximo de 5 colunas por linha
            row = idx // 5
            
            comp = ModernGauge(self.gauges_frame, width=190, height=120, 
                               title=gauge_data["title"], unit=gauge_data["unit"], 
                               min_val=gauge_data["min"], max_val=gauge_data["max"], 
                               arc_color=cor)
            comp.grid(row=row, column=col, padx=2, pady=5)
            self.componentes_visuais[spn] = comp

        # === ÁREA DE ESTATÍSTICAS (O NOVO PAINEL) ===
        self.stats_frame = ctk.CTkFrame(self.main_content, fg_color="#212121", corner_radius=8)
        self.stats_frame.grid(row=2, column=0, sticky="ew", pady=(0, 20))
        self.stats_frame.grid_columnconfigure((0,1,2,3,4,5), weight=1)

        # Labels das Métricas (Abreviadas e ajustadas para caber em 1 linha)
        self.lbl_stat_rx = ctk.CTkLabel(self.stats_frame, text="Rx: 0", font=("Arial", 11, "bold"))
        self.lbl_stat_rx.grid(row=0, column=0, padx=2, pady=10)

        self.lbl_stat_dec = ctk.CTkLabel(self.stats_frame, text="Decod: 0", font=("Arial", 11, "bold"), text_color="#2ecc71")
        self.lbl_stat_dec.grid(row=0, column=1, padx=2, pady=10)

        self.lbl_stat_perc = ctk.CTkLabel(self.stats_frame, text="Sucesso: 0.0%", font=("Arial", 11, "bold"))
        self.lbl_stat_perc.grid(row=0, column=2, padx=2, pady=10)

        self.lbl_stat_tps = ctk.CTkLabel(self.stats_frame, text="Taxa: 0 msg/s", font=("Arial", 11, "bold"))
        self.lbl_stat_tps.grid(row=0, column=3, padx=2, pady=10)

        self.lbl_stat_time_rx = ctk.CTkLabel(self.stats_frame, text="Int. Rx: 0.0 ms", font=("Arial", 11))
        self.lbl_stat_time_rx.grid(row=0, column=4, padx=2, pady=10)

        self.lbl_stat_time_dec = ctk.CTkLabel(self.stats_frame, text="T. Decod: 0.0 ms", font=("Arial", 11))
        self.lbl_stat_time_dec.grid(row=0, column=5, padx=2, pady=10)

        # === TABS LOGS ===
        self.tabview = ctk.CTkTabview(self.main_content)
        self.tabview.grid(row=3, column=0, sticky="nsew")
        self.tabview.add("Decodificado")
        self.tabview.add("Bruto (Raw)")
        
        self.txt_decod = ctk.CTkTextbox(self.tabview.tab("Decodificado"), font=("Consolas", 12))
        self.txt_decod.pack(fill="both", expand=True)
        self.txt_raw = ctk.CTkTextbox(self.tabview.tab("Bruto (Raw)"), font=("Consolas", 12))
        self.txt_raw.pack(fill="both", expand=True)

    def toggle_silent_mode(self):
        if self.switch_silent.get() == 1:
            self.led_ack.configure(fg_color="#00FF00") 
            self.lbl_ack.configure(text="Seguro (No ACK)", text_color="white")
        else:
            self.led_ack.configure(fg_color="#FFAA00") 
            self.lbl_ack.configure(text="ACK ATIVO (Cuidado)", text_color="#FFAA00")

    def toggle_connection(self):
        if not self.is_connected:
            # CONECTAR
            self.is_connected = True
            self.btn_connect.configure(text="DESCONECTAR", fg_color="#c0392b", hover_color="#a93226")
            self.led_conn.configure(fg_color="#00FF00")
            self.lbl_conn.configure(text="Conectado")
            self.led_rec.configure(text_color="#FF0000")
            
            # Bloqueios
            self.combo_interface.configure(state="disabled")
            self.combo_bitrate.configure(state="disabled")
            self.switch_loop.configure(state="disabled")
            self.switch_silent.configure(state="disabled")
            self.btn_test_frame.configure(state="normal")
                       
        else:
            # DESCONECTAR
            self.is_connected = False
            self.btn_connect.configure(text="CONECTAR CAN", fg_color="#2e8b57", hover_color="#1e5b38")
            self.led_conn.configure(fg_color="red")
            self.lbl_conn.configure(text="Desconectado")
            self.led_rec.configure(text_color="gray")
            
            # Desbloqueios
            self.combo_interface.configure(state="normal")
            self.combo_bitrate.configure(state="normal")
            self.switch_loop.configure(state="normal")
            self.switch_silent.configure(state="normal")
            self.btn_test_frame.configure(state="disabled")

    def send_test_frame(self):
        print("Enviando frame teste...")

class MKSApp(ctk.CTk):
    def __init__(self, on_ready_callback=None):
        super().__init__()
        self.title("MKS Master System - Mestrado")
        self.geometry("1024x768")
        
        # Guarda a função que o main.py passou para chamar depois
        self.on_ready_callback = on_ready_callback
        
        # Inicia Splash
        self.show_splash()

    def show_splash(self):
        SplashScreenFrame(self, on_finish_callback=self.show_main_interface)

    def show_main_interface(self):
        # Cria a interface principal
        self.main_frame = MainInterfaceFrame(self)
        
        # AGORA SIM o main_frame existe.
        # Se o main.py pediu para ser avisado, avisamos agora:
        if self.on_ready_callback:
            self.on_ready_callback()

if __name__ == "__main__":
    if not os.path.exists("assets"): os.makedirs("assets")
    app = MKSApp()
    app.mainloop()
    if not os.path.exists("assets"): os.makedirs("assets")
    app = MKSApp()
    app.mainloop()
