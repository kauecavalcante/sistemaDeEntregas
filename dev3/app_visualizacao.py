import folium
import json
import os
import requests
from branca.element import Template, MacroElement

# ---- FUNÇÃO PARA DECODIFICAR POLYLINE (usada pela API de roteamento) ----
# Esta função converte uma string de polyline (formato compacto) em uma lista de coordenadas lat/lon.
# Fonte: https://stackoverflow.com/questions/27670984/how-to-decode-a-polyline-string-into-lat-lon-points-in-python
def decode_polyline(polyline_str):
    index, lat, lng = 0, 0, 0
    coordinates = []
    while index < len(polyline_str):
        b = 0
        shift = 0
        result = 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if result & 1 else (result >> 1)
        lat += dlat

        b = 0
        shift = 0
        result = 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if result & 1 else (result >> 1)
        lng += dlng

        coordinates.append((lat / 100000.0, lng / 100000.0))
    return coordinates


def get_route_from_osrm(start_coords, end_coords):
    # OSRM Public API (não para produção, uso limitado e pode ser bloqueado)
    # Formato: http://router.project-osrm.org/route/v1/driving/longitude,latitude;longitude,latitude
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=full&geometries=polyline"
    
    try:
        response = requests.get(url)
        response.raise_for_status() 
        data = response.json()
        
        if data['code'] == 'Ok':
            
            encoded_polyline = data['routes'][0]['geometry']
            
            return decode_polyline(encoded_polyline)
        else:
            print(f"Erro ao obter rota do OSRM: {data.get('code')}: {data.get('message')}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Erro de conexão com o OSRM: {e}")
        return None
    except Exception as e:
        print(f"Erro inesperado: {e}")
        return None


def criar_painel(dados):
    rotas_criticas = sorted(
        dados['arestas'],
        key=lambda x: x['fluxo_atual'] / x['capacidade'],
        reverse=True
    )[:3]  
    
    total_pacotes = sum(aresta['fluxo_atual'] for aresta in dados['arestas'])
    
    painel_html = f"""
    <div style="position: fixed; left: 10px; top: 10px; width: 250px; 
                background: white; padding: 10px; z-index: 1000;
                border: 1px solid #ccc; font-family: Arial; border-radius: 5px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);">
        <h4 style="margin:0; color: #333;">📊 Painel de Controle</h4>
        <hr style="margin: 10px 0;">
        <p style="margin:5px 0;">📦 <b>Total de pacotes:</b> {total_pacotes}</p>
        <h5 style="margin:10px 0 5px 0; color: #d9534f;">🚨 Rotas Críticas:</h5>
        <ol style="padding-left: 20px; margin-top: 0;">
    """
    
    for rota in rotas_criticas:
        origem = next(v['nome'] for v in dados['vertices'] if v['id'] == rota['origem'])
        destino = next(v['nome'] for v in dados['vertices'] if v['id'] == rota['destino'])
        percentual = int(100 * rota['fluxo_atual'] / rota['capacidade'])
        cor = "#d9534f" if percentual > 90 else "#f0ad4e" if percentual > 70 else "#5cb85c"
        painel_html += f"""
            <li style="margin-bottom: 8px;">
                <b>{origem} → {destino}</b><br>
                <div style="background: #f5f5f5; border-radius: 3px; height: 15px;">
                    <div style="background: {cor}; width: {percentual}%; height: 100%; border-radius: 3px;"></div>
                </div>
                <small>{rota['fluxo_atual']}/{rota['capacidade']} ({percentual}%)</small>
            </li>
        """
    
    painel_html += """
        </ol>
        <hr style="margin: 10px 0;">
        <small style="color: #999;">Atualizado em: </small>
    </div>
    """
    return painel_html

caminho_json = os.path.join('dados_ficticios', 'rede_entregas.json')
with open(caminho_json) as f:
    dados = json.load(f)


map_center = [-23.5505, -46.6333] # Coordenada inicial do Centro de Distribuição SP
mapa = folium.Map(location=map_center, zoom_start=13, tiles="CartoDB positron")

template = """
{% macro html(this, kwargs) %}
<div style="position: fixed; top: 10px; right: 10px; width: 180px; 
            background: white; padding: 10px; z-index: 1000;
            border: 1px solid #ddd; border-radius: 5px; font-family: Arial;">
    <h4 style="margin:0; font-size: 14px;">📦 Rede de Entregas</h4>
    <hr style="margin: 8px 0;">
    <p style="margin:5px 0;"><i class="fa fa-truck" style="color: #4285F4;"></i> Depósito</p>
    <p style="margin:5px 0;"><i class="fa fa-warehouse" style="color: #0F9D58;"></i> Hub</p>
    <p style="margin:5px 0;"><i class="fa fa-home" style="color: #FF9800;"></i> Zona</p>
    <p style="margin:5px 0;"><span style="color: #0F9D58;">━━━</span> Rota normal</p>
    <p style="margin:5px 0;"><span style="color: #d9534f;">━━━</span> Rota crítica</p>
</div>
{% endmacro %}
"""
macro = MacroElement()
macro._template = Template(template)
mapa.get_root().add_child(macro)

for vertice in dados['vertices']:
    if vertice['tipo'] == 'deposito':
        icone = folium.Icon(icon='truck', prefix='fa', color='blue')
        status = "🟢 Operação normal"
    elif vertice['tipo'] == 'hub':
        icone = folium.Icon(icon='warehouse', prefix='fa', color='green')
        status = "🟡 Em análise"
    else:
        icone = folium.Icon(icon='home', prefix='fa', color='orange')
        status = "🔴 Alta demanda"
    
    popup_content = f"""
    <b>{vertice['nome']}</b><br>
    Tipo: {vertice['tipo']}<br>
    Status: {status}<br>
    <button onclick="alert('Relatório gerado para {vertice['nome']}')" 
            style="background: #4285F4; color: white; border: none; padding: 5px 10px; border-radius: 3px;">
        Detalhes
    </button>
    """
    folium.Marker(
        location=[vertice['lat'], vertice['lon']],
        popup=folium.Popup(popup_content, max_width=250),
        icon=icone
    ).add_to(mapa)

# ---- ROTAS (AGORA CHAMANDO OSRM) ----
for aresta in dados['arestas']:
    origem_vertice = next(v for v in dados['vertices'] if v['id'] == aresta['origem'])
    destino_vertice = next(v for v in dados['vertices'] if v['id'] == aresta['destino'])
    
    start_coords = [origem_vertice['lat'], origem_vertice['lon']]
    end_coords = [destino_vertice['lat'], destino_vertice['lon']]
    
    # Chama a função para obter a rota real do OSRM
    caminho_real = get_route_from_osrm(start_coords, end_coords)
    
    capacidade_ociosa = aresta['capacidade'] - aresta['fluxo_atual']
    
    tooltip_content = f"""
    <b>Rota: {origem_vertice['nome']} → {destino_vertice['nome']}</b><br>
    Capacidade: {aresta['capacidade']} pacotes/hora<br>
    Fluxo atual: {aresta['fluxo_atual']}<br>
    <span style="color: {'#d9534f' if capacidade_ociosa < 0 else '#0F9D58'}">
        {'⚠️ SOBRECARREGADA' if capacidade_ociosa < 0 else f'🟢 {capacidade_ociosa} livres'}
    </span>
    """
    
    if caminho_real:
        folium.PolyLine(
            locations=caminho_real, # Usa a rota real do OSRM
            color='#d9534f' if capacidade_ociosa < 0 else '#0F9D58',
            weight=5,
            tooltip=tooltip_content
        ).add_to(mapa)
    else:
        
        print(f"Não foi possível obter a rota OSRM para {origem_vertice['nome']} para {destino_vertice['nome']}. Desenhando linha reta.")
        folium.PolyLine(
            locations=[start_coords, end_coords],
            color='gray', 
            weight=3,
            tooltip=f"ROTA INDISPONÍVEL: {tooltip_content}"
        ).add_to(mapa)



macro_painel = MacroElement()
macro_painel._template = Template(criar_painel(dados))
mapa.get_root().add_child(macro_painel)


mapa.save('mapa.html')
print("Mapa gerado!✅ Abra 'mapa.html' no navegador.")