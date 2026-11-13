#include <SPI.h>
#include <mcp_can.h>

// O pino CS (Chip Select) padrão dos módulos MCP2515 geralmente é o 10 no Arduino Uno
const int spiCSPin = 10;
MCP_CAN CAN(spiCSPin);

void setup() {
    Serial.begin(500000);
    
    // Configuração para Rede J1939 de Tratores (250kbps, oscilador de 8MHz padrão do módulo chinês)
    while (CAN_OK != CAN.begin(CAN_250KBPS, MCP_8MHz)) {
        Serial.println("Falha ao iniciar o controlador MCP2515. Tentando novamente...");
        delay(500);
    }
    Serial.println("MCP2515 Inicializado com Sucesso!");
}

void loop() {
    // Escuta a porta serial vinda do Python
    if (Serial.available()) {
        String dado = Serial.readStringUntil('\n');
        
        int virgula_pos = dado.indexOf(',');
        
        if (virgula_pos > 0) {
            String id_str = dado.substring(0, virgula_pos);
            String payload_str = dado.substring(virgula_pos + 1);
            
            // Converte ID Hex (String) para Inteiro
            long can_id = strtol(id_str.c_str(), NULL, 16);
            
            // Calcula o tamanho (DLC) - Cada 2 caracteres hex equivalem a 1 byte
            byte dlc = payload_str.length() / 2;
            byte data[8];
            
            // Converte o Payload Hex (String) para array de bytes
            for (int i = 0; i < dlc; i++) {
                String byte_str = payload_str.substring(i * 2, i * 2 + 2);
                data[i] = (byte) strtol(byte_str.c_str(), NULL, 16);
            }
            
            // Injeta na rede física! (Formato Estendido (1) exigido pelo J1939)
            CAN.sendMsgBuf(can_id, 1, dlc, data);
        }
    }
}