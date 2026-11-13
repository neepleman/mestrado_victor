import customtkinter as ctk

class StatusLEDArray(ctk.CTkFrame):
    def __init__(self, master, title, max_val, width=100, height=100, **kwargs):
        super().__init__(master, width=width, height=height, fg_color="#2b2b2b", corner_radius=5, **kwargs)
        self.grid_propagate(False) 
        self.pack_propagate(False)
        
        # --- DEBUG E PROTEÇÃO ---
        print(f"[LED DEBUG] Inicializando '{title}' | max_val recebido: {max_val}")
        
        try:
            self.max_val = int(float(max_val))
        except (ValueError, TypeError):
            print(f"[LED ERRO] max_val inválido para '{title}'. Forçando valor para 3.")
            self.max_val = 3
            
        # Trava de segurança física da tela: Se pedir mais de 15 LEDs, limitamos para não borrar
        if self.max_val > 15:
            print(f"[LED AVISO] '{title}' pediu {self.max_val} LEDs! Limitando a 7 para caber no Canvas.")
            self.max_val = 7
        # ------------------------

        self.leds = {} 
        self.current_value = -1 
        
        short_title = title if len(title) <= 25 else title[:22] + "..."
        ctk.CTkLabel(self, text=short_title, font=("Arial", 12, "bold"), text_color="#aaaaaa").pack(pady=(5, 0))
        
        self.canvas_w = width - 10
        self.canvas = ctk.CTkCanvas(self, bg="#2b2b2b", highlightthickness=0, height=50, width=self.canvas_w)
        self.canvas.pack(fill="x", padx=5, pady=5)
        
        self._draw_leds_static()

    def _draw_leds_static(self):
        self.canvas.delete("all")
        total_leds = self.max_val + 1 
        
        print(f"[LED DEBUG] Desenhando {total_leds} LEDs (incluindo UD) para '{self.winfo_name()}'")
        
        spacing = self.canvas_w / (total_leds + 1)
        
        # Raio dinâmico: se tiver muitos LEDs, eles diminuem de tamanho para não encavalar
        r = min(8, (spacing / 2) - 2)
        if r < 2: r = 2 
        
        for i in range(total_leds):
            cx = spacing * (i + 1)
            cy = 20
            
            is_ud = (i == self.max_val)
            color = "#444444" 
            label_text = "UD" if is_ud else str(i)
            
            led_id = self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, fill=color, outline="#111111", width=2)
            
            # Só desenha o textinho embaixo se houver espaço (ou se for o de UD)
            if total_leds <= 8:
                self.canvas.create_text(cx, cy+18, text=label_text, fill="#aaaaaa", font=("Arial", 9))
            elif is_ud:
                self.canvas.create_text(cx, cy+18, text="UD", fill="#aaaaaa", font=("Arial", 8))

            self.leds[i] = led_id

    def set_value(self, value):
        self.current_value = value
        for i, led_id in self.leds.items():
            if str(value) == "UD" and i == self.max_val:
                self.canvas.itemconfig(led_id, fill="#e74c3c") 
            elif str(value) != "UD" and float(value) == i:
                self.canvas.itemconfig(led_id, fill="#2ecc71") 
            else:
                self.canvas.itemconfig(led_id, fill="#444444")
