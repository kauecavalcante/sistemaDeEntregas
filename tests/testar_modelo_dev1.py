from src.core.modelo_rede import RedeLogistica
import os
import json 

def main():
    print("--- Testando o Módulo de Modelagem (Dev 1) ---")

    
    caminho_json = os.path.join('dev3', 'dados_ficticios', 'rede_base.json')
    
    
    try:
        minha_rede = RedeLogistica.carregar_de_json(caminho_json)
    except (FileNotFoundError, ValueError, KeyError) as e:
        return

    
    try:
        minha_rede.validar_integridade()
    except (ValueError, ConnectionError) as e:
        print(f"Falha na validação da rede: {e}")
        return

   
    print("\nConvertendo a rede para o formato da API do Dev 5...")
    dados_para_api = minha_rede.para_dicionario_api()
    print("Dados prontos para enviar:")
   
    print(json.dumps(dados_para_api, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()