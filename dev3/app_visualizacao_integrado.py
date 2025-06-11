import folium
import json
import os
import requests
from branca.element import Template, MacroElement

# URL API dev 5
API_BASE_URL = "http://127.0.0.1:8000"


def decode_polyline(polyline_str):
    index, lat, lng = 0, 0, 0
    coordinates = []
    while index < len(polyline_str):
        b, shift, result = 0, 0, 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20: break
        dlat = ~(result >> 1) if result & 1 else (result >> 1)
        lat += dlat
        b, shift, result = 0, 0, 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20: break
        dlng = ~(result >> 1) if result & 1 else (result >> 1)
        lng += dlng
        coordinates.append((lat / 100000.0, lng / 100000.0))
    return coordinates

def get_route_from_osrm(start_coords, end_coords):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=full&geometries=polyline"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data['code'] == 'Ok':
            return decode_polyline(data['routes'][0]['geometry'])
    except requests.exceptions.RequestException as e:
        print(f"Aviso: Não foi possível conectar ao OSRM para traçar rota. {e}")
    return None

def criar_painel(dados_analise):
    rotas_criticas = sorted(
        dados_analise['rotas_com_fluxo'],
        key=lambda x: (x['fluxo'] / x['capacidade']) if x['capacidade'] > 0 else 0,
        reverse=True
    )[:3]
    
    painel_html = f"""
    <div style="position: fixed; left: 10px; top: 10px; width: 250px; 
                background: white; padding: 10px; z-index: 1000;
                border: 1px solid #ccc; font-family: Arial; border-radius: 5px;">
        <h4 style="margin:0; color: #333;">📊 Painel de Controle</h4>
        <p style="margin:5px 0;">🌊 <b>Fluxo Máximo:</b> {dados_analise['fluxo_maximo']}</p>
        <h5 style="margin:10px 0 5px 0; color: #d9534f;">🚨 Rotas com Maior Carga:</h5>
        <ol style="padding-left: 20px; margin-top: 0;">"""
    
    for rota in rotas_criticas:
        if rota['origem'] is None or rota['destino'] is None: continue
        percentual = int(100 * rota['fluxo'] / rota['capacidade']) if rota['capacidade'] > 0 else 0
        cor = "#d9534f" if percentual > 90 else "#f0ad4e" if percentual > 70 else "#5cb85c"
        painel_html += f"""
            <li style="margin-bottom: 8px;">
                <b>{rota['origem']} → {rota['destino']}</b><br>
                <div style="background: #f5f5f5; border-radius: 3px; height: 15px;">
                    <div style="background: {cor}; width: {percentual}%; height: 100%;"></div>
                </div>
                <small>{rota['fluxo']}/{rota['capacidade']} ({percentual}%)</small>
            </li>"""
    painel_html += "</ol></div>"
    return painel_html

#  CARREGAR DADOS BASE (SEM FLUXO) 
caminho_json_base = os.path.join('dados_ficticios', 'rede_base.json')
with open(caminho_json_base) as f:
    rede_base = json.load(f)

#  CHAMAR A API DO DEV 5 PARA OBTER DADOS COM FLUXO CALCULADO 
try:
    print("  Enviando configuração de rede para a sua API...")
    requests.post(f"{API_BASE_URL}/rede", json=rede_base)
    
    print("  Solicitando cálculo de fluxo...")
    response = requests.post(f"{API_BASE_URL}/fluxo/calcular")
    response.raise_for_status()
    
    dados_da_api = response.json()
    print("  Dados com fluxo calculado recebidos da API!")

except requests.exceptions.RequestException as e:
    print(f"❌ ERRO: Não foi possível conectar à sua API em {API_BASE_URL}. Verifique se ela está rodando.")
    print(f"Detalhe: {e}")
    exit()


map_data = {
    "vertices": rede_base['vertices'],
    "arestas": dados_da_api['rotas_com_fluxo']
}


deposito_inicial = next((v for v in map_data['vertices'] if v['tipo'] == 'deposito'), None)

if deposito_inicial:
    map_center = [deposito_inicial['lat'], deposito_inicial['lon']]
    print(f"🗺️  Mapa centralizado em '{deposito_inicial['nome']}' ({map_center})")
else:
    # Fallback caso nenhum depósito seja encontrado no JSON
    map_center = [-15.78, -47.92] # Centro do Brasil
    print("⚠️  Nenhum depósito encontrado. Centralizando o mapa no Brasil.")

mapa = folium.Map(location=map_center, zoom_start=13, tiles="CartoDB positron")


# (Legenda - sem alterações)
template_legenda = "{% macro html(this, kwargs) %}<div style='position: fixed; top: 10px; right: 10px; width: 180px; background: white; padding: 10px; z-index: 1000; border: 1px solid #ddd; border-radius: 5px; font-family: Arial;'><h4 style='margin:0; font-size: 14px;'>📦 Rede de Entregas</h4><hr style='margin: 8px 0;'><p style='margin:5px 0;'><i class='fa fa-truck' style='color: #4285F4;'></i> Depósito</p><p style='margin:5px 0;'><i class='fa fa-warehouse' style='color: #0F9D58;'></i> Hub</p><p style='margin:5px 0;'><i class='fa fa-home' style='color: #FF9800;'></i> Zona</p><p style='margin:5px 0;'><span style='color: #0F9D58;'>━━━</span> Rota Normal</p><p style='margin:5px 0;'><span style='color: #d9534f;'>━━━</span> Rota Crítica</p></div>{% endmacro %}"
macro_legenda = MacroElement()
macro_legenda._template = Template(template_legenda)
mapa.get_root().add_child(macro_legenda)


for vertice in map_data['vertices']:
    if vertice['tipo'] == 'deposito': icone = folium.Icon(icon='truck', prefix='fa', color='blue')
    elif vertice['tipo'] == 'hub': icone = folium.Icon(icon='warehouse', prefix='fa', color='green')
    else: icone = folium.Icon(icon='home', prefix='fa', color='orange')
    popup_content = f"<b>{vertice['nome']}</b><br>Tipo: {vertice['tipo']}"
    folium.Marker(location=[vertice['lat'], vertice['lon']], popup=popup_content, icon=icone).add_to(mapa)

# Rotas
vertices_dict = {v['nome']: v for v in map_data['vertices']}
for aresta in map_data['arestas']:
    if aresta['origem'] is None or aresta['destino'] is None: continue
    
    origem_vertice = vertices_dict[aresta['origem']]
    destino_vertice = vertices_dict[aresta['destino']]
    
    start_coords = [origem_vertice['lat'], origem_vertice['lon']]
    end_coords = [destino_vertice['lat'], destino_vertice['lon']]
    caminho_real = get_route_from_osrm(start_coords, end_coords)
    
    carga = (aresta['fluxo'] / aresta['capacidade']) if aresta['capacidade'] > 0 else 0
    cor_rota = '#d9534f' if carga > 0.9 else '#f0ad4e' if carga > 0.7 else '#0F9D58'

    tooltip_content = f"<b>Rota: {aresta['origem']} → {aresta['destino']}</b><br>Fluxo: {aresta['fluxo']}<br>Capacidade: {aresta['capacidade']}"
    
    folium.PolyLine(
        locations=caminho_real if caminho_real else [start_coords, end_coords],
        color=cor_rota,
        weight=2 + (carga * 6),
        tooltip=tooltip_content
    ).add_to(mapa)


macro_painel = MacroElement()
macro_painel._template = Template(criar_painel(dados_da_api))
mapa.get_root().add_child(macro_painel)


mapa.save('mapa_INTEGRADO.html')
print("✅ Mapa integrado gerado! Abra 'mapa_INTEGRADO.html' no navegador.")