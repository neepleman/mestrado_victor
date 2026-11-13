import csv
import os
from datetime import datetime

class DataLogger:
    def __init__(self, log_folder="logs"):
        self.log_folder = log_folder
        self.raw_file = None
        self.decod_file = None
        self.writer_raw = None
        self.writer_decod = None
        self.is_recording = False
        
        if not os.path.exists(log_folder):
            os.makedirs(log_folder)

    def start_new_session(self):
        """Cria novos arquivos com Timestamp no nome"""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Arquivo Bruto
        path_raw = f"{self.log_folder}/raw_{timestamp}.csv"
        self.raw_file = open(path_raw, 'w', newline='')
        self.writer_raw = csv.writer(self.raw_file)
        self.writer_raw.writerow(["Timestamp", "ID_HEX", "DLC", "DADOS_HEX"]) # Cabeçalho
        
        # Arquivo Decodificado
        path_decod = f"{self.log_folder}/decoded_{timestamp}.csv"
        self.decod_file = open(path_decod, 'w', newline='')
        self.writer_decod = csv.writer(self.decod_file)
        self.writer_decod.writerow(["Timestamp", "PGN_Nome", "Valor", "Unidade"]) # Cabeçalho
        
        self.is_recording = True
        print(f"[LOGGER] Gravando em: {timestamp}")

    def log_raw(self, timestamp_str, can_id, dlc, data_hex):
        if self.is_recording and self.writer_raw:
            self.writer_raw.writerow([timestamp_str, can_id, dlc, data_hex])

    def log_decoded(self, timestamp_str, nome_pgn, valor, unidade):
        if self.is_recording and self.writer_decod:
            self.writer_decod.writerow([timestamp_str, nome_pgn, valor, unidade])
            
    def stop(self):
        self.is_recording = False
        if self.raw_file: self.raw_file.close()
        if self.decod_file: self.decod_file.close()
        print("[LOGGER] Gravação finalizada.")