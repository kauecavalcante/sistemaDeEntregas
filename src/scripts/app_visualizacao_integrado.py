import folium
import json
import os
import requests
from branca.element import Template, MacroElement
import random


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API_BASE_URL = "http://127.0.0.1:8000"

NOME_ARQUIVO_MAPA = os.path.join(ROOT_DIR, "outputs", "mapa_roteirizado.html") 


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
    return [start_coords, end_coords] 


caminho_json_base = os.path.join(ROOT_DIR, 'data', 'rede_base.json')

with open(caminho_json_base, encoding='utf-8') as f:
    rede_base = json.load(f)

# Montar o problema de roteirização (VRP)
print("🛠️  Montando o problema de roteirização (VRP)...")
coordenadas = {v['nome']: (v['lat'], v['lon']) for v in rede_base['vertices']}
deposito_nome = rede_base['fontes'][0]

demandas = {v['nome']: random.randint(5, 25) for v in rede_base['vertices'] if v['tipo'] == 'zona'}
demandas[deposito_nome] = 0

problema_vrp = {
    "coordenadas": coordenadas,
    "demandas": demandas,
    "num_veiculos": 4,
    "capacidade_veiculo": 50,
    "nome_deposito": deposito_nome
}


try:
    print("📞 Enviando problema para o endpoint /roteirizar da sua API...")
    response = requests.post(f"{API_BASE_URL}/roteirizar", json=problema_vrp, timeout=90.0)
    response.raise_for_status()
    solucao_vrp = response.json()
    print("✅ Solução de roteirização recebida com sucesso!")

except requests.exceptions.RequestException as e:
    print(f"❌ ERRO: Não foi possível conectar à sua API em {API_BASE_URL}/roteirizar.")
    print(f"Detalhe: {e}")
    exit()


map_center = coordenadas[deposito_nome]
mapa = folium.Map(location=map_center, zoom_start=13, tiles="CartoDB positron")

# Adicionar marcadores dos locais
icones = {'deposito': 'truck', 'hub': 'warehouse', 'zona': 'home'}
cores_icones = {'deposito': 'blue', 'hub': 'green', 'zona': 'orange'}
for v in rede_base['vertices']:
    folium.Marker(
        location=[v['lat'], v['lon']],
        popup=f"<b>{v['nome']}</b><br>Tipo: {v['tipo']}<br>Demanda: {demandas.get(v['nome'], 0)} pacotes",
        icon=folium.Icon(icon=icones[v['tipo']], prefix='fa', color=cores_icones[v['tipo']])
    ).add_to(mapa)

# Desenhar as rotas otimizadas dos veículos
cores_rotas = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
for i, rota_info in enumerate(solucao_vrp['rotas_otimizadas']):
    cor = cores_rotas[i % len(cores_rotas)]
    pontos_da_rota = rota_info['rota']
    caminho_completo = []

    for j in range(len(pontos_da_rota) - 1):
        origem = coordenadas[pontos_da_rota[j]]
        destino = coordenadas[pontos_da_rota[j+1]]
        segmento = get_route_from_osrm(origem, destino)
        caminho_completo.extend(segmento)

    
    tooltip_content = (f"<b>Veículo {rota_info['veiculo_id']}</b><br>"
                       f"Carga: {rota_info['carga_total']}<br>"
                       f"Distância: {rota_info['distancia_metros']/1000:.2f} km<br>"
                       f"Paradas: {' -> '.join(p for p in pontos_da_rota)}")
    
    folium.PolyLine(
        locations=caminho_completo,
        color=cor,
        weight=5,
        opacity=0.8,
        tooltip=tooltip_content
    ).add_to(mapa)


dist_total_km = solucao_vrp['distancia_total_metros'] / 1000
num_veiculos_usados = len(solucao_vrp['rotas_otimizadas'])

painel_html = f"""
 <div style="position: fixed; top: 10px; right: 10px; width: 250px; 
             background: white; padding: 10px; z-index: 1000;
             border: 2px solid #333; border-radius: 8px; font-family: Arial;">
     <h4 style="margin:0; color: #333; border-bottom: 1px solid #ccc; padding-bottom: 5px;">
         🚚 Plano de Roteirização
     </h4>
     <p style="margin:8px 0;"><b>Veículos em rota:</b> {num_veiculos_usados} de {problema_vrp['num_veiculos']}</p>
     <p style="margin:8px 0;"><b>Distância Total:</b> {dist_total_km:.2f} km</p>
     <hr style='margin: 8px 0;'>
     <h5 style='margin:10px 0 5px 0; font-size: 14px;'>Legenda das Rotas:</h5>
"""
for i, rota_info in enumerate(solucao_vrp['rotas_otimizadas']):
    cor = cores_rotas[i % len(cores_rotas)]
    painel_html += f"<p style='margin:3px 0;'><span style='background-color:{cor}; border-radius: 50%; display: inline-block; width: 12px; height: 12px;'></span> Veículo {rota_info['veiculo_id']}</p>"
painel_html += "</div>"

macro_painel = MacroElement()
macro_painel._template = Template(painel_html)
mapa.get_root().add_child(macro_painel)



mapa.save(NOME_ARQUIVO_MAPA)
print(f"✅ Mapa de roteirização gerado! Abra '{NOME_ARQUIVO_MAPA}' no navegador.")