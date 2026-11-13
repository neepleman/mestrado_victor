import serial
import csv
import time

# Configurações do seu Setup
PORTA_SERIAL = 'COM3'  # Altere para a porta real do seu Arduino
BAUD_RATE = 115200
ARQUIVO_CSV = 'log_kuhn_accura.csv' # Seu log real do implemento

def iniciar_simulacao():
    print("[INJETOR] Abrindo porta serial e aguardando Arduino...")
    arduino = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=1)
    time.sleep(2) # Tempo vital para o Arduino reiniciar após conectar a serial
    
    print("[INJETOR] Simulação Trace-Driven Iniciada!")
    
    with open(ARQUIVO_CSV, mode='r', encoding='utf-8-sig') as f:
        leitor = csv.DictReader(f)
        
        # Usa o relógio de alta precisão do processador
        tempo_inicio_real = time.perf_counter()
        tempo_inicio_log = 0.0 
        primeira_linha = True
        
        for linha in leitor:
            try:
                can_id = linha['ID'].strip()
                payload = linha['Payload'].replace(" ", "").strip()
                
                # Monta o pacote simplificado para a Serial
                # Formato esperado pelo Arduino: "18FEEF00,FFFFFFFFFFFFFFFF\n"
                pacote = f"{can_id},{payload}\n"
                
                # Se você tiver a coluna de Timestamp em milissegundos no CSV, 
                # a lógica do perf_counter (cronômetro de alta precisão) entra aqui 
                # para segurar o loop até dar o tempo exato de enviar a mensagem.
                
                arduino.write(pacote.encode('utf-8'))
                
                # Pequeno delay de segurança para não afogar o buffer do Arduino
                time.sleep(0.001) 
                
            except Exception as e:
                print(f"Erro ao injetar linha: {e}")

    print("[INJETOR] Fim do arquivo de log alcançado.")
    arduino.close()

if __name__ == "__main__":
    iniciar_simulacao()