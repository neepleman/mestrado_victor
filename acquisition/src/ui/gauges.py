import customtkinter as ctk

class ModernGauge(ctk.CTkFrame):
    def __init__(self, master, title="Gauge", unit="", min_val=0, max_val=100, 
                 width=180, height=150, arc_color="#3498db", 
                 font_title=("Arial", 11, "bold"), font_value=("Arial", 14, "bold"), **kwargs):
        
        super().__init__(master, width=width, height=height, fg_color="#2b2b2b", corner_radius=10, **kwargs)
        self.grid_propagate(False)
        self.pack_propagate(False)

        self.min_val = float(min_val)
        self.max_val = float(max_val)
        self.unit = unit

        # Higieniza o título para não estourar a caixa
        short_title = title if len(title) <= 25 else title[:22] + "..."
        ctk.CTkLabel(self, text=short_title, font=font_title, text_color="#aaaaaa").pack(pady=(5,0))

        # Canvas para desenhar o arco
        # Deixa uma margem para o arco respirar
        self.canvas_size = min(width - 5, height - 35) 
        self.canvas = ctk.CTkCanvas(self, width=width, height=self.canvas_size, bg="#2b2b2b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Centro do Canvas
        cx = width / 2
        cy = self.canvas_size / 2 + 30

        # Texto do valor no meio
        self.value_label = self.canvas.create_text(cx, cy, text=f"- {unit}", fill="#ffffff", font=font_value)

        # Coordenadas da "caixa" do arco (Bounding Box)
        pad_x = (width - self.canvas_size) / 5
        self.bbox = (pad_x, 10, width - pad_x, self.canvas_size + 10)

        # Desenha o fundo cinza (180 graus)
        self.canvas.create_arc(self.bbox, start=0, extent=180, style="arc", outline="#444444", width=8)
        
        # Cria o arco colorido vazio (que vai preencher dinamicamente)
        self.arc_id = self.canvas.create_arc(self.bbox, start=180, extent=0, style="arc", outline=arc_color, width=8)

    def set_value(self, value):
        try:
            val = float(value)
        except ValueError:
            self.canvas.itemconfig(self.value_label, text="UD")
            self.canvas.itemconfig(self.arc_id, extent=0)
            return

        # Proteção matemática para a escala
        span = self.max_val - self.min_val
        if span == 0: span = 1

        # Limita o ponteiro fisicamente (se o trator der 110 RPM num painel de 100, o ponteiro trava no fundo)
        draw_val = max(self.min_val, min(self.max_val, val))
        
        # Calcula a porcentagem de preenchimento
        percentage = (draw_val - self.min_val) / span

        # Tkinter desenha arcos no sentido anti-horário. 
        # Começamos em 180 (Esquerda/9h) e subtraímos em graus negativos até 0 (Direita/3h)
        extent_angle = - (percentage * 180)
        self.canvas.itemconfig(self.arc_id, extent=extent_angle)

        # Atualiza o texto de forma inteligente (Se for ,0 não mostra decimal)
        if val.is_integer():
            texto = f"{int(val)} {self.unit}"
        else:
            texto = f"{val:.1f} {self.unit}"
            
        self.canvas.itemconfig(self.value_label, text=texto)
