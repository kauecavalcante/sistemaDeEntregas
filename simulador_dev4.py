import json
import requests
import os
import copy
from fpdf import FPDF 
from datetime import datetime


API_BASE_URL = "http://127.0.0.1:8000"
CAMINHO_REDE_BASE = os.path.join('dev3', 'dados_ficticios', 'rede_base.json')
NOME_ARQUIVO_PDF = "Relatorio_de_Simulacao_de_Rede.pdf"

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Sistema de Otimização de Rede de Entregas', 0, 1, 'C')
        self.set_font('Arial', '', 8)
        self.cell(0, 5, f'Relatório Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 14)
        self.set_fill_color(230, 230, 230)
        self.cell(0, 10, f'Cenário: {title}', 0, 1, 'L', fill=True)
        self.ln(5)

    def chapter_body(self, resultado):
        if not resultado:
            self.set_font('Arial', '', 12)
            self.multi_cell(0, 10, 'Não foi possível gerar o relatório pois não há resultados.')
            return

        fluxo_maximo = resultado.get('fluxo_maximo', 0)
        rotas = resultado.get('rotas_com_fluxo', [])

        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, f'Fluxo Máximo Total: {fluxo_maximo} pacotes/hora', 0, 1)
        self.ln(5)
        
        gargalos = []
        rotas_ociosas = []

        for rota_atual in rotas:
            if rota_atual.get('origem') is None or rota_atual.get('destino') is None: continue
            capacidade = rota_atual.get('capacidade', 0)
            fluxo = rota_atual.get('fluxo', 0)
            if capacidade > 0:
                utilizacao = (fluxo / capacidade) * 100
                if utilizacao >= 99.9:
                    gargalos.append((rota_atual, utilizacao))
                elif fluxo > 0:
                    rotas_ociosas.append((rota_atual, utilizacao))
        
        
        self.set_font('Arial', 'B', 11)
        self.cell(0, 10, 'Gargalos Identificados (Rotas em ~100%)', 0, 1)
        if gargalos:
            self.set_font('Arial', '', 10)
            for rota, utilizacao in gargalos:
                linha = f"- Rota: {rota['origem']} -> {rota['destino']} ({rota['fluxo']}/{rota['capacidade']} | {utilizacao:.0f}%)"
                self.cell(0, 5, linha, 0, 1)
        else:
            self.set_font('Arial', 'I', 10)
            self.cell(0, 5, '   Nenhum gargalo encontrado.', 0, 1)
        
        self.ln(5)

       
        self.set_font('Arial', 'B', 11)
        self.cell(0, 10, 'Rotas com Capacidade Ociosa', 0, 1)
        if rotas_ociosas:
            rotas_ociosas.sort(key=lambda item: item[1])
            self.set_font('Arial', '', 10)
            for rota, utilizacao in rotas_ociosas:
                linha = f"- Rota: {rota['origem']} -> {rota['destino']} ({rota['fluxo']}/{rota['capacidade']} | {utilizacao:.2f}%)"
                self.cell(0, 5, linha, 0, 1)
        else:
            self.set_font('Arial', 'I', 10)
            self.cell(0, 5, '   Nenhuma rota ociosa com fluxo.', 0, 1)
        
        self.ln(10)


def executar_calculo_fluxo(rede_config: dict) -> dict:
    try:
        requests.post(f"{API_BASE_URL}/rede", json=rede_config)
        response = requests.post(f"{API_BASE_URL}/fluxo/calcular")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None

def simular_e_gerar_pdf():
    try:
        with open(CAMINHO_REDE_BASE) as f:
            rede_base = json.load(f)
    except FileNotFoundError:
        print(f"ERRO: Arquivo de rede base não encontrado em '{CAMINHO_REDE_BASE}'")
        return

    print("--- Iniciando Simulação Avançada e Geração de PDF (Dev 4) ---")
    
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, 'Relatório de Análise de Cenários', 0, 1, 'C')
    pdf.ln(10)

    # CENÁRIO 1: NORMAL
    print("1. Analisando Condições Normais...")
    resultado_normal = executar_calculo_fluxo(rede_base)
    pdf.chapter_title("Condições Normais")
    pdf.chapter_body(resultado_normal)

    # CENÁRIO 2: BLOQUEIO
    print("2. Simulando Bloqueio de Rota...")
    rede_bloqueio = copy.deepcopy(rede_base)
    rota_bloqueada = {"origem": "Hub Paulista", "destino": "Zona Centro"}
    for rota in rede_bloqueio['rotas']:
        if rota['origem'] == rota_bloqueada['origem'] and rota['destino'] == rota_bloqueada['destino']:
            rota['capacidade'] = 0
    resultado_bloqueio = executar_calculo_fluxo(rede_bloqueio)
    pdf.chapter_title(f"Bloqueio da Rota '{rota_bloqueada['origem']} -> {rota_bloqueada['destino']}'")
    pdf.chapter_body(resultado_bloqueio)

    # CENÁRIO 3: AUMENTO DE DEMANDA
    print("3. Simulando Aumento de Demanda...")
    rede_demanda = copy.deepcopy(rede_base)
    for rota in rede_demanda['rotas']:
        if rota['origem'] == "Centro de Distribuição SP":
            rota['capacidade'] *= 2
    resultado_demanda = executar_calculo_fluxo(rede_demanda)
    pdf.chapter_title("Aumento de Oferta/Demanda (x2 na saída do depósito)")
    pdf.chapter_body(resultado_demanda)

    # CENÁRIO 4: ROTA PRIORITÁRIA
    print("4. Simulando Rota Prioritária...")
    rede_prioridade = copy.deepcopy(rede_base)
    rota_prioritaria = {"origem": "Centro de Distribuição SP", "destino": "Zona Jardins", "capacidade": 500}
    rede_prioridade['rotas'].append(rota_prioritaria)
    resultado_prioridade = executar_calculo_fluxo(rede_prioridade)
    pdf.chapter_title("Criação de Rota Prioritária para 'Zona Jardins'")
    pdf.chapter_body(resultado_prioridade)
    
    
    try:
        pdf.output(NOME_ARQUIVO_PDF)
        print("\n" + "="*60)
        print(f"✅ SUCESSO! Relatório em PDF gerado com o nome: {NOME_ARQUIVO_PDF}")
        print("="*60)
    except Exception as e:
        print(f"ERRO: Falha ao salvar o arquivo PDF. Detalhe: {e}")


if __name__ == "__main__":
    simular_e_gerar_pdf()