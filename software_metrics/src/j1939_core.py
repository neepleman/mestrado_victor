import csv
from bitstring import BitArray

class J1939Parser:
    def __init__(self, caminho_dicionario):
        """
        Ao instanciar o parser, ele carrega a base de dados na RAM.
        Isso acontece apenas uma vez no ciclo de vida do programa.
        """
        self.caracteres_hex_validos = set("0123456789ABCDEFabcdef")
        self.regras_pgn, self.nomes_pgn = self._carregar_dicionario_ram(caminho_dicionario)

    def _parse_start_bit(self, start_bit_str):
        start_bit_str = str(start_bit_str).replace(',', '.')
        try:
            byte_str, bit_str = start_bit_str.split('.')
            return int(byte_str), int(bit_str)
        except:
            return 1, 1

    def _safe_float(self, val_str, default=0.0):
        """
        Higieniza valores matemáticos corrompidos pelo Excel.
        Remove espaços, pontos duplicados e converte vírgulas.
        """
        val_str = str(val_str).strip()
        if not val_str or val_str.upper() == 'NULL':
            return default
            
        # 1. Remove espaços em branco perdidos
        val_str = val_str.replace(' ', '')
        
        # 2. Remove vírgulas ou pontos "sobrando" no final (ex: "0," vira "0")
        val_str = val_str.rstrip(',.')
        
        # 3. Transforma todas as vírgulas em pontos
        val_str = val_str.replace(',', '.')
        
        # 4. Resolve a mutação dos múltiplos pontos (ex: "-156.865.234.375")
        if val_str.count('.') > 1:
            partes = val_str.split('.')
            # Mantém o primeiro ponto como decimal e junta o resto (vira "-156.865234375")
            val_str = partes[0] + '.' + "".join(partes[1:])
            
        try:
            return float(val_str)
        except ValueError:
            return default

    def _carregar_dicionario_ram(self, caminho):
        regras = {}
        nomes = {}
        with open(caminho, mode='r', encoding='latin-1') as file:
            reader = csv.DictReader(file, delimiter=';') 
            for row in reader:
                pgn_str = row.get('pgn', '').strip()
                try: pgn_int = int(pgn_str)
                except ValueError: continue
                    
                if pgn_int not in nomes:
                    nomes[pgn_int] = row.get('pg_label', '').strip()
                
                length_str = str(row.get('max', '0')).strip()
                is_raw = not length_str or length_str == 'NULL'
                
                regra = {
                    'is_raw': is_raw,
                    'spn': row.get('spn', ''),
                    'sp_label': row.get('sp_label', 'NULL').replace('NULL', '').strip(),
                    'start_byte': self._parse_start_bit(row.get('sp_start_bit', '1.1'))[0] if not is_raw else 1,
                    'start_bit': self._parse_start_bit(row.get('sp_start_bit', '1.1'))[1] if not is_raw else 1,
                    'tamanho_bits': int(length_str) if not is_raw else 0,
                    'scale': self._safe_float(row.get('scale', '1'), 1.0),
                    'offset': self._safe_float(row.get('offset', '0'), 0.0),
                    'unit': row.get('unit', 'NULL').replace('NULL', '').strip(),
                    'type': row.get('type', 'NULL').replace('NULL', '').strip() if not is_raw else 'Bruto',
                    'scaling_txt': row.get('scaling_txt', '').strip(),
                }
                
                if pgn_int not in regras: regras[pgn_int] = []
                regras[pgn_int].append(regra)
        return regras, nomes

    def _extrair_pgn(self, id_hex):
        id_int = int(id_hex, 16)
        pf = (id_int >> 16) & 0xFF
        ps = (id_int >> 8) & 0xFF
        return pf << 8 if pf < 240 else (pf << 8) | ps

    def _higienizar_payload(self, payload_hex):
        if not all(c in self.caracteres_hex_validos for c in payload_hex):
            return "".join([c if c in self.caracteres_hex_validos else 'F' for c in payload_hex])
        return payload_hex

    def decodificar_mensagem(self, id_hex, payload_hex):
        """
        A ÚNICA PORTA DE ENTRADA DO PARSER.
        Recebe ID e Payload em Hexadecimal.
        Retorna uma lista de dicionários contendo os dados extraídos.
        """
        resultados = []
        pgn = self._extrair_pgn(id_hex)
        pg_label = self.nomes_pgn.get(pgn, "Desconhecido")
        payload_hex = self._higienizar_payload(payload_hex)
        
        # Mensagem Cega ou Multipacote
        if len(payload_hex) > 16 or pgn not in self.regras_pgn:
            return [{
                'pgn': pgn, 'pg_label': pg_label, 'spn': 'N/A', 
                'sp_label': 'Mensagem Desconhecida', 'valor': payload_hex, 
                'unidade': '', 'tipo': 'Bruto'
            }]
            
        payload_bits = BitArray(hex=payload_hex)
        
        for regra in self.regras_pgn[pgn]:
            if regra['is_raw']:
                resultados.append({
                    'pgn': pgn, 'pg_label': pg_label, 'spn': regra['spn'], 
                    'sp_label': regra['sp_label'], 'valor': payload_hex, 
                    'unidade': regra['unit'], 'tipo': regra['type']
                })
                continue
                
            byte_num, bit_num, tamanho = regra['start_byte'], regra['start_bit'], regra['tamanho_bits']
            
            inicio = (byte_num - 1) * 8 + (8 - bit_num - tamanho + 1) if tamanho <= 8 else (byte_num - 1) * 8
            fim = inicio + tamanho
            
            if fim > len(payload_bits): continue
                
            bloco_extraido = payload_bits[inicio:fim]
            
            if tamanho > 8 and tamanho % 8 == 0:
                bytes_invertidos = [bloco_extraido[i:i+8] for i in range(0, tamanho, 8)][::-1]
                bloco_extraido = BitArray().join(bytes_invertidos)
                
            valorbrutodec = bloco_extraido.uint
            limite_maximo = (1 << tamanho) - 1 
            
            if valorbrutodec == limite_maximo:
                valor_final = "UD"
            else:
                valor_final = round((valorbrutodec * regra['scale']) + regra['offset'], 3)
                
            resultados.append({
                'pgn': pgn, 'pg_label': pg_label, 'spn': regra['spn'], 
                'sp_label': regra['sp_label'], 'valor': valor_final, 
                'unidade': regra['unit'], 'tipo': regra['type'],
                'scaling_txt': regra.get('scaling_txt', '')
            })
            
        return resultados