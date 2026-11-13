import serial
import time
import os

# CONFIGURAÇÕES 
PORTA_SERIAL = 'COM10'  
BAUD_RATE = 500000
ARQUIVO_LOG = 'log_comercial_trator.txt'

def injetar_log_na_bancada():
    print(f"Conectando ao Arduino na porta {PORTA_SERIAL}...")
    try:
        # Inicia a conexão Serial
        arduino = serial.Serial(PORTA_SERIAL, BAUD_RATE, timeout=1)
        time.sleep(2) # Dá um tempo pro Arduino reiniciar ao plugar
        print(arduino.readline().decode('utf-8').strip()) # Lê a msg de sucesso do MCP
    except Exception as e:
        print(f"Erro na porta Serial: {e}")
        return

    diretorio_atual = os.path.dirname(os.path.abspath(__file__))
    caminho_log = os.path.join(diretorio_atual, ARQUIVO_LOG)

    if not os.path.exists(caminho_log):
        print(f"Arquivo {ARQUIVO_LOG} não encontrado!")
        return

    print(f"Iniciando injeção do log Khun Accura na bancada HIL...")
    
    tempo_anterior_log = None
    cronometro_inicio = time.perf_counter()
    mensagens_enviadas = 0

    with open(caminho_log, 'r', encoding='utf-8') as f:
        for linha in f:
            linha = linha.strip()
            if not linha: continue
            
            try:
                # Extrai os pedaços: (1759942179.172935) can0 0CF00400#10BDBD3C4B00FFBD
                partes = linha.split(' ')
                timestamp_str = partes[0].replace('(', '').replace(')', '')
                timestamp_atual_log = float(timestamp_str)
                
                id_e_dados = partes[2].split('#')
                can_id = id_e_dados[0]
                can_data = id_e_dados[1]
                
                # --- A MÁGICA DO TEMPO EXACTO ---
                if tempo_anterior_log is not None:
                    delta_log = timestamp_atual_log - tempo_anterior_log
                    
                    # Usa busy-wait para precisão de milissegundos/microssegundos (time.sleep falha no Windows)
                    alvo_cronometro = cronometro_inicio + delta_log
                    while time.perf_counter() < alvo_cronometro:
                        pass # Trava o Python por micro-segundos até a hora exata
                
                # Atualiza os relógios para o próximo ciclo
                tempo_anterior_log = timestamp_atual_log
                cronometro_inicio = time.perf_counter()
                
                # Formata a string e envia pelo cabo USB para o Arduino
                comando_serial = f"{can_id},{can_data}\n"
                arduino.write(comando_serial.encode('ascii'))
                
                mensagens_enviadas += 1
                if mensagens_enviadas % 1000 == 0:
                    print(f"{mensagens_enviadas} mensagens enviadas...")

            except Exception as e:
                pass # Ignora linhas zoadas do log

    print(f"FIM DA SIMULAÇÃO! {mensagens_enviadas} pacotes disparados na rede CAN.")
    arduino.close()

if __name__ == "__main__":
    injetar_log_na_bancada()