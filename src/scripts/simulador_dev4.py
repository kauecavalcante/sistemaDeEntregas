import json
import requests
import os
import copy
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from datetime import datetime
import random


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API_BASE_URL = "http://127.0.0.1:8000"

NOME_ARQUIVO_PDF = os.path.join(ROOT_DIR, "outputs", "Relatorio_Simulacao_de_Roteirizacao.pdf")


class PDF(FPDF):
    """ Classe customizada para gerar o relatório em PDF. """
    def header(self):
        self.set_font('helvetica', 'B', 12)
        self.cell(0, 10, 'Sistema de Otimização de Rotas de Entrega', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.set_font('helvetica', '', 8)
        self.cell(0, 5, f'Relatório Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', align='C')

    def chapter_title(self, title):
        self.set_font('helvetica', 'B', 14)
        self.set_fill_color(220, 220, 255)
        self.cell(0, 10, f'Cenário: {title}', new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True, align='L')
        self.ln(5)

    def chapter_body_vrp(self, resultado):
        """ Função para escrever o corpo do capítulo com resultados do VRP. """
        if not resultado or 'rotas_otimizadas' not in resultado:
            self.set_font('helvetica', 'I', 12)
            self.multi_cell(0, 10, 'Não foi possível encontrar uma solução para este cenário.')
            self.ln(10)
            return

        self.set_font('helvetica', 'B', 12)
        dist_total_km = resultado['distancia_total_metros'] / 1000
        num_veiculos = len(resultado['rotas_otimizadas'])
        self.cell(0, 8, f"Veículos Utilizados: {num_veiculos}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 8, f"Distância Total Percorrida: {dist_total_km:.2f} km", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)

        self.set_font('helvetica', 'B', 11)
        self.cell(0, 10, 'Detalhes das Rotas dos Veículos:', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for rota_info in resultado['rotas_otimizadas']:
            self.set_font('helvetica', 'B', 10)
            dist_rota_km = rota_info['distancia_metros'] / 1000
            linha_veiculo = (f"  - Veículo {rota_info['veiculo_id']}: "
                             f"{dist_rota_km:.2f} km | Carga: {rota_info['carga_total']}")
            self.cell(0, 7, linha_veiculo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            self.set_font('helvetica', '', 9)
            paradas = ' -> '.join(rota_info['rota'])
            self.multi_cell(0, 5, f"    Paradas: {paradas}", align='L')
            self.ln(2)
        
        self.ln(10)

def executar_calculo_roteirizacao(problema_vrp: dict) -> dict:
    """ Envia um problema VRP para a API e retorna a solução. """
    try:
        response = requests.post(f"{API_BASE_URL}/roteirizar", json=problema_vrp, timeout=30.0)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"  [AVISO] Falha ao executar cenário: {e}")
        return None

def simular_e_gerar_pdf_vrp():
    """ Função principal que executa os cenários de VRP e gera o PDF. """
    
    caminho_rede_base = os.path.join(ROOT_DIR, 'data', 'rede_base.json')
    
    try:
        with open(caminho_rede_base, encoding='utf-8') as f:
            rede_base = json.load(f)
    except FileNotFoundError:
        print(f"ERRO: Arquivo de rede base não encontrado em '{caminho_rede_base}'")
        return

    print("--- Iniciando Simulação de Cenários de Roteirização (VRP) ---")

    coordenadas = {v['nome']: (v['lat'], v['lon']) for v in rede_base['vertices']}
    deposito_nome = rede_base['fontes'][0]
    demandas_base = {v['nome']: random.randint(10, 30) for v in rede_base['vertices'] if v['tipo'] == 'zona'}
    demandas_base[deposito_nome] = 0

    problema_base_vrp = {
        "coordenadas": coordenadas,
        "demandas": demandas_base,
        "num_veiculos": 4,
        "capacidade_veiculo": 60,
        "nome_deposito": deposito_nome
    }
    
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('helvetica', 'B', 16)
    pdf.cell(0, 10, 'Relatório de Simulação de Roteirização', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(10)

    # CENÁRIO 1: OPERAÇÃO NORMAL
    print("1. Simulando Cenário: Operação Normal...")
    solucao_normal = executar_calculo_roteirizacao(problema_base_vrp)
    pdf.chapter_title("Operação Normal")
    pdf.chapter_body_vrp(solucao_normal)

    # CENÁRIO 2: FROTA REDUZIDA (1 VEÍCULO QUEBRADO)
    print("2. Simulando Cenário: Frota Reduzida...")
    problema_frota_reduzida = copy.deepcopy(problema_base_vrp)
    problema_frota_reduzida['num_veiculos'] -= 1
    solucao_frota_reduzida = executar_calculo_roteirizacao(problema_frota_reduzida)
    pdf.chapter_title(f"Frota Reduzida ({problema_frota_reduzida['num_veiculos']} veículos)")
    pdf.chapter_body_vrp(solucao_frota_reduzida)

    # CENÁRIO 3: DEMANDA DE PICO (+50% NAS ENTREGAS)
    print("3. Simulando Cenário: Demanda de Pico...")
    problema_pico = copy.deepcopy(problema_base_vrp)
    for zona in problema_pico['demandas']:
        if problema_pico['demandas'][zona] > 0:
            problema_pico['demandas'][zona] = int(problema_pico['demandas'][zona] * 1.5)
    solucao_pico = executar_calculo_roteirizacao(problema_pico)
    pdf.chapter_title("Demanda de Pico (+50%)")
    pdf.chapter_body_vrp(solucao_pico)

    # CENÁRIO 4: CAPACIDADE REDUZIDA (VEÍCULOS MENORES)
    print("4. Simulando Cenário: Capacidade de Veículos Reduzida...")
    problema_capacidade = copy.deepcopy(problema_base_vrp)
    problema_capacidade['capacidade_veiculo'] = 40 # Capacidade original era 60
    solucao_capacidade = executar_calculo_roteirizacao(problema_capacidade)
    pdf.chapter_title(f"Capacidade de Veículos Reduzida ({problema_capacidade['capacidade_veiculo']} pacotes)")
    pdf.chapter_body_vrp(solucao_capacidade)
    
    try:
        pdf.output(NOME_ARQUIVO_PDF)
        print("\n" + "="*60)
        print(f"✅ SUCESSO! Relatório de Roteirização gerado: {NOME_ARQUIVO_PDF}")
        print("="*60)
    except Exception as e:
        print(f"ERRO: Falha ao salvar o arquivo PDF. Detalhe: {e}")


if __name__ == "__main__":
    simular_e_gerar_pdf_vrp()