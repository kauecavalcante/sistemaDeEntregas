# Módulo de Visualização (Dev 3)
- **Arquivo principal**: `app_visualizacao.py`
- **Dependências**: folium, branca
- **Como integrar**:
  1. O backend (Dev 5) deve fornecer um endpoint `/rede-atual` retornando:
     ```json
     {
       "vertices": [...],
       "arestas": [{"origem": "id1", "destino": "id2", "capacidade": 100, "fluxo_atual": 85}]
     }
     ```
  2. Substituir a função de carregar dados por uma chamada à API.