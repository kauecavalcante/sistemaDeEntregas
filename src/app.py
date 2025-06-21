import streamlit as st
import json
import requests
import os
import glob
import random
import pandas as pd
import folium
import streamlit.components.v1 as components
import time
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos

st.set_page_config(layout="wide", page_title="Otimizador de Entregas")
API_BASE_URL = "http://127.0.0.1:8000"

class PDF(FPDF):
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

def gerar_relatorio_pdf(solucao, problema):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('helvetica', 'B', 16)
    pdf.cell(0, 10, 'Relatório de Otimização de Rotas', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(10)
    pdf.set_font('helvetica', 'B', 12)
    num_veiculos_usados = len(solucao['rotas_otimizadas'])
    dist_total_km = solucao.get('distancia_total_metros', 0) / 1000
    pdf.cell(0, 8, f"Veículos Utilizados: {num_veiculos_usados} de {problema['num_veiculos']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 8, f"Distância Total Percorrida: {dist_total_km:.2f} km", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if 'custo_total' in solucao:
        pdf.cell(0, 8, f"Custo Total Estimado: R$ {solucao['custo_total']:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(10)
    pdf.set_font('helvetica', 'B', 11)
    pdf.cell(0, 10, 'Plano de Rotas por Veículo:', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    for rota in solucao['rotas_otimizadas']:
        pdf.set_font('helvetica', 'B', 10)
        dist_rota_km = rota['distancia_metros'] / 1000
        linha_veiculo = f"  - Veículo {rota['veiculo_id']}: {dist_rota_km:.2f} km | Carga: {rota['carga_total']} pacotes"
        if 'custo_rota' in rota:
            linha_veiculo += f" | Custo: R$ {rota['custo_rota']:.2f}"
        pdf.cell(0, 7, linha_veiculo, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('helvetica', '', 9)
        paradas = " -> ".join([f"{p['local']} ({p['horario_chegada']})" for p in rota['rota']])
        pdf.multi_cell(0, 5, f"    Paradas: {paradas} -> Depósito", align='L')
        pdf.ln(3)
    return bytes(pdf.output())

def geocode_enderecos(df):
    st.info("Iniciando geocodificação dos endereços... Isso pode levar um tempo.")
    geolocator = Nominatim(user_agent=f"otimizador_entregas_{random.randint(1000,9999)}")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1, error_wait_seconds=10)
    coordenadas, progress_text, progress_bar, total = {}, st.empty(), st.progress(0), len(df)
    for i, row in enumerate(df.itertuples(index=False)):
        endereco_atual = row.Endereço
        try:
            location = geocode(f"{endereco_atual}, Maceió, AL, Brasil", timeout=20)
            coordenadas[endereco_atual] = (location.latitude, location.longitude) if location else None
        except Exception as e:
            st.error(f"Erro ao geocodificar '{endereco_atual}': {e}")
            coordenadas[endereco_atual] = None
        progress_text.text(f"Geocodificando: {i + 1} de {total} endereços.")
        progress_bar.progress((i + 1) / total)
    progress_text.empty(); st.success("Geocodificação concluída!")
    return {k: v for k, v in coordenadas.items() if v}

def chamar_api_roteirizacao(problema_vrp):
    try:
        response = requests.post(f"{API_BASE_URL}/roteirizar", json=problema_vrp, timeout=90.0)
        response.raise_for_status(); return response.json()
    except requests.exceptions.RequestException as e:
        if hasattr(e, 'response') and e.response is not None:
            st.error(f"Erro da API ({e.response.status_code}): {e.response.text}")
        else: st.error(f"Erro de Conexão com a API: {e}")
        return None

def criar_mapa_folium(solucao, problema):
    coordenadas, deposito_nome = problema['coordenadas'], problema['nome_deposito']
    if deposito_nome not in coordenadas: return None
    mapa = folium.Map(location=coordenadas[deposito_nome], zoom_start=14, tiles="CartoDB positron")
    for nome, coord in coordenadas.items():
        if coord: folium.Marker(location=coord, popup=f"<b>{nome}</b>", icon=folium.Icon(icon='home' if nome != deposito_nome else 'truck', prefix='fa', color='blue' if nome == deposito_nome else 'orange')).add_to(mapa)
    cores = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
    for i, rota in enumerate(solucao['rotas_otimizadas']):
        caminho = []
        locais_rota = [p['local'] for p in rota['rota']]
        for j in range(len(locais_rota) - 1):
            local_atual, local_seguinte = locais_rota[j], locais_rota[j+1]
            if local_atual in coordenadas and local_seguinte in coordenadas:
                 time.sleep(0.2) 
                 segmento = get_route_from_osrm(coordenadas[local_atual], coordenadas[local_seguinte])
                 if segmento: caminho.extend(segmento)
        if caminho: folium.PolyLine(locations=caminho, color=cores[i % len(cores)], weight=5, opacity=0.8, tooltip=f"Veículo {rota['veiculo_id']}").add_to(mapa)
    return mapa

def get_route_from_osrm(c1, c2):
    if not c1 or not c2: return None
    url = f"http://router.project-osrm.org/route/v1/driving/{c1[1]},{c1[0]};{c2[1]},{c2[0]}?overview=full&geometries=polyline"
    try:
        r = requests.get(url, timeout=15); r.raise_for_status(); data = r.json()
        if data.get('code') == 'Ok' and data.get('routes'):
            return decode_polyline(data['routes'][0]['geometry'])
    except Exception as e:
        st.warning(f"Aviso: Não foi possível desenhar o caminho exato. Mostrando linha reta. (Erro: {e})", icon="⚠️")
        return [c1, c2]
    return [c1, c2]

def decode_polyline(polyline_str):
    index, lat, lng = 0, 0, 0
    coordinates = []
    changes = {'lat': 0, 'lng': 0}
    while index < len(polyline_str):
        for unit in ['lat', 'lng']:
            shift, result = 0, 0
            while True:
                if index >= len(polyline_str): return coordinates
                byte = ord(polyline_str[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if not byte >= 0x20: break
            if result & 1: changes[unit] = ~(result >> 1)
            else: changes[unit] = (result >> 1)
        lat += changes['lat']
        lng += changes['lng']
        coordinates.append((lat / 100000.0, lng / 100000.0))
    return coordinates

st.title("🚚 Sistema de Otimização de Entregas")
st.sidebar.title("⚙️ Configurações da Otimização")

uploaded_file = st.sidebar.file_uploader("1. Arquivo de Entregas (.csv)", type=["csv"])
if 'df_entregas' not in st.session_state: st.session_state['df_entregas'] = None
if uploaded_file: st.session_state['df_entregas'] = pd.read_csv(uploaded_file).fillna('')

if st.session_state.get('df_entregas') is not None:
    df_entregas = st.session_state['df_entregas']
    df_entregas['Endereço'] = df_entregas['Endereço'].str.strip()
    deposito_selecionado = st.sidebar.selectbox("2. Selecione o Endereço do Depósito", df_entregas["Endereço"].tolist())
    
    st.sidebar.subheader("Frota e Operação")
    num_veiculos = st.sidebar.number_input("Número de Veículos", min_value=1, value=4)
    capacidade_veiculo = st.sidebar.number_input("Capacidade por Veículo (unidades)", min_value=1, value=50)
    tempo_servico = st.sidebar.number_input("Tempo de Parada em cada entrega (minutos)", min_value=0, value=5)

    st.sidebar.subheader("Otimizações Avançadas")
    balanceamento_map = {"Nenhum": "nenhum", "Por Tempo de Rota": "tempo", "Por Distância da Rota": "distancia"}
    balancear_por = st.sidebar.selectbox(
        "Balancear Carga de Trabalho",
        options=list(balanceamento_map.keys())
    )
    balancear_por_valor = balanceamento_map[balancear_por]

    st.sidebar.subheader("Parâmetros de Custo")
    consumo_kml = st.sidebar.number_input("Consumo médio do veículo (km/L)", min_value=0.1, value=10.0, format="%.2f")
    preco_combustivel = st.sidebar.number_input("Preço do combustível (R$/L)", min_value=0.01, value=5.99, format="%.2f")
    custo_hora_motorista = st.sidebar.number_input("Custo da mão-de-obra (R$/hora)", min_value=0.0, value=20.0, format="%.2f")

    if st.sidebar.button("Otimizar Rotas", type="primary", use_container_width=True):
        if deposito_selecionado:
            coordenadas = geocode_enderecos(df_entregas)
            if deposito_selecionado not in coordenadas:
                st.error("Endereço do depósito não encontrado após geocodificação.")
            else:
                demandas = pd.Series(df_entregas.Pacotes.values, index=df_entregas.Endereço).to_dict()
                demandas[deposito_selecionado] = 0
                
                janelas_de_tempo = {row.Endereço: (int(row.Janela_Inicio.split(':')[0])*3600, int(row.Janela_Fim.split(':')[0])*3600) for row in df_entregas.itertuples() if 'Janela_Inicio' in df_entregas.columns and row.Janela_Inicio and row.Janela_Fim}
                
                prioridades = {
                    row.Endereço: int(row.Prioridade)
                    for row in df_entregas.itertuples()
                    if 'Prioridade' in df_entregas.columns and pd.notna(row.Prioridade) and str(row.Prioridade).strip() != ''
                }
                
                custo_por_km = (preco_combustivel / consumo_kml) if consumo_kml > 0 else 0
                
                problema_vrp = {
                    "coordenadas": coordenadas, "demandas": demandas, "num_veiculos": num_veiculos,
                    "capacidade_veiculo": capacidade_veiculo, "nome_deposito": deposito_selecionado, 
                    "janelas_de_tempo": janelas_de_tempo, "tempo_servico": tempo_servico * 60,
                    "custo_km": custo_por_km, "custo_hora": custo_hora_motorista,
                    "prioridades": prioridades,
                    "balancear_carga_por": balancear_por_valor
                }
                
                st.session_state['problema_vrp'] = problema_vrp
                with st.spinner("Otimizando rotas..."):
                    solucao = chamar_api_roteirizacao(problema_vrp)
                    st.session_state['solucao_vrp'] = solucao
                    if solucao:
                        st.success("Otimização concluída!")
                        st.rerun()
        else:
            st.sidebar.warning("Por favor, selecione um depósito.")

    st.sidebar.markdown("---")
    if st.sidebar.button("Limpar Caches", use_container_width=True):
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        files_to_remove = glob.glob(os.path.join(data_dir, 'matriz_*.json'))
        if files_to_remove:
            for f in files_to_remove: os.remove(f)
            st.sidebar.success(f"{len(files_to_remove)} caches de matrizes limpos!")
        else:
            st.sidebar.info("Nenhum cache para limpar.")
        if 'solucao_vrp' in st.session_state: del st.session_state['solucao_vrp']
        st.rerun()

if 'solucao_vrp' in st.session_state and st.session_state['solucao_vrp']:
    st.header("Resultados da Otimização")
    solucao = st.session_state['solucao_vrp']
    problema = st.session_state['problema_vrp']
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Veículos Utilizados", f"{len(solucao['rotas_otimizadas'])} de {problema['num_veiculos']}")
    col2.metric("Distância Total", f"{solucao.get('distancia_total_metros', 0) / 1000:.2f} km")
    if 'custo_total' in solucao:
        col3.metric("Custo Total Estimado", f"R$ {solucao['custo_total']:.2f}")

    mapa = criar_mapa_folium(solucao, problema)
    if mapa:
        components.html(mapa._repr_html_(), height=500, scrolling=True)
    
    st.subheader("Plano de Rotas por Veículo")
    rotas_formatadas = []
    for rota in solucao['rotas_otimizadas']:
        paradas_str = " -> ".join([f"{p['local']} ({p['horario_chegada']})" for p in rota['rota']])
        dados_rota = {
            "Veículo": rota['veiculo_id'], "Carga (unid.)": rota['carga_total'], 
            "Distância (km)": f"{rota['distancia_metros']/1000:.2f}",
            "Paradas (com horário)": paradas_str + " -> Depósito"
        }
        if 'custo_rota' in rota:
            dados_rota["Custo da Rota (R$)"] = f"{rota['custo_rota']:.2f}"
        rotas_formatadas.append(dados_rota)
    
    df_rotas = pd.DataFrame(rotas_formatadas)
    st.dataframe(df_rotas, use_container_width=True, hide_index=True)
    
    st.subheader("Exportar Resultados")
    col1_down, col2_down = st.columns(2)
    with col1_down:
        csv = df_rotas.to_csv(index=False).encode('utf-8')
        st.download_button("Baixar Plano (CSV)", csv, 'plano_de_rotas.csv', 'text/csv', use_container_width=True)
    with col2_down:
        pdf_data = gerar_relatorio_pdf(solucao, problema)
        st.download_button("Baixar Relatório (PDF)", pdf_data, "relatorio_otimizacao.pdf", "application/pdf", use_container_width=True)
    
    with st.expander("Ver dados da solução em formato JSON"):
        st.json(solucao)




# streamlit run src/app.py