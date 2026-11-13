import csv
import json
import os

def gerar_configuracao():
    print("=== GERADOR DE CONFIG PARA INTERFACE ===")
    entrada = input("Digite os SPNs que deseja na tela, separados por vírgula (ex: 190, 598, 110, 92): ")
    spns_alvo = [s.strip() for s in entrada.split(",") if s.strip().isdigit()]
    
    if not spns_alvo:
        print("Nenhum SPN válido inserido. Encerrando.")
        return

    caminho_csv = "pgn_config.csv" # Ajuste o caminho se necessário
    if not os.path.exists(caminho_csv):
        print(f"Erro: Arquivo '{caminho_csv}' não encontrado!")
        return

    config_final = {"gauges": [], "leds": []}
    spns_encontrados = set()

    with open(caminho_csv, mode='r', encoding='latin-1') as f:
        # Se o seu CSV usa ponto e vírgula, mantenha delimiter=';'
        reader = csv.DictReader(f, delimiter=';') 
        
        for row in reader:
            spn_atual = str(row.get('SPN', row.get('spn', ''))).strip()
            
            if spn_atual in spns_alvo and spn_atual not in spns_encontrados:
                spns_encontrados.add(spn_atual)
                
                titulo = row.get('SP_Label', row.get('sp_label', 'Desconhecido'))
                unidade = row.get('Unit', row.get('unit', ''))
                scaling_txt = str(row.get('Scaling_Txt', row.get('scaling_txt', ''))).lower()
                
                # Regra do "Chapéu Seletor" que criamos no Windows
                if "states" in scaling_txt:
                    # É um LED
                    try: bits = int(row.get('SP_Length', 2))
                    except: bits = 2
                    max_val = (1 << bits) - 1
                    
                    config_final["leds"].append({
                        "spn": int(spn_atual),
                        "title": titulo,
                        "max_val": max_val
                    })
                else:
                    # É um Gauge (Calcula o Mínimo e Máximo Físico)
                    try: scale = float(str(row.get('Scale', '1')).replace(',', '.'))
                    except: scale = 1.0
                    try: offset = float(str(row.get('Offset', '0')).replace(',', '.'))
                    except: offset = 0.0
                    try: bits = int(row.get('SP_Length', 8))
                    except: bits = 8
                    
                    max_raw = (1 << bits) - 1
                    val_max_fisico = (max_raw * scale) + offset
                    
                    config_final["gauges"].append({
                        "spn": int(spn_atual),
                        "title": titulo,
                        "unit": unidade,
                        "min": offset,
                        "max": val_max_fisico
                    })

    # Salva o arquivo final
    with open("ui_config.json", "w", encoding="utf-8") as f:
        json.dump(config_final, f, indent=4, ensure_ascii=False)
        
    print(f"\n[SUCESSO] ui_config.json gerado! Encontrados {len(spns_encontrados)} de {len(spns_alvo)} SPNs.")
    print("Copie este arquivo para a pasta raiz da sua Raspberry Pi.")

if __name__ == "__main__":
    gerar_configuracao()
