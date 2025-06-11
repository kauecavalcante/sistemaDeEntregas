import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any

class Rota(BaseModel):
    origem: str
    destino: str
    capacidade: int = Field(gt=0)

class RedeDeEntrega(BaseModel):
    fontes: List[str]
    sumidouros: List[str]
    rotas: List[Rota]


app = FastAPI(
    title="Delivery Routing Optimizer API (Backend Principal)",
    description="API que integra a modelagem, o cálculo de fluxo (Dev2) e a visualização.",
    version="1.2.0" 
)

# URL pública da API de cálculo de fluxo do Dev2
DEV2_FLUXO_API_URL = "https://fluxo-maximo-api.onrender.com/fluxo-maximo"

# Armazenamento em Memória (simples)
db: Dict[str, Any] = {
    "rede_formatada_usuario": None,
    "resultado_fluxo": None
}

@app.post("/rede")
def configurar_rede(rede: RedeDeEntrega):
    """
    Endpoint para receber a configuração da rede de entregas.
    """
    db["rede_formatada_usuario"] = rede.dict()
    db["resultado_fluxo"] = None
    return {"mensagem": f"Rede com {len(rede.rotas)} rotas configurada com sucesso."}


@app.post("/fluxo/calcular", summary="Dispara o cálculo de fluxo máximo chamando a API do Dev2")
async def calcular_fluxo():
    """
    Este endpoint faz o seguinte:
    1. Pega a rede configurada (com nomes, ex: "Deposito_A").
    2. Traduz essa rede para o formato que a API do Dev2 espera (com índices numéricos).
    3. Envia uma requisição POST para a API do Dev2.
    4. Recebe o resultado com índices numéricos.
    5. Traduz o resultado de volta para o formato com nomes.
    6. Armazena e retorna o resultado final.
    """
    rede_usuario = db.get("rede_formatada_usuario")
    if not rede_usuario:
        raise HTTPException(status_code=400, detail="A rede não foi configurada. Use o endpoint /rede primeiro.")

    nodes = sorted(list(set(
        [r['origem'] for r in rede_usuario['rotas']] + 
        [r['destino'] for r in rede_usuario['rotas']] +
        rede_usuario['fontes'] +
        rede_usuario['sumidouros']
    )))
    mapa_nome_para_indice = {nome: i for i, nome in enumerate(nodes)}
    
    payload_para_dev2 = {
        "nodeCount": len(nodes),
        "sources": [mapa_nome_para_indice[nome] for nome in rede_usuario['fontes']],
        "sinks": [mapa_nome_para_indice[nome] for nome in rede_usuario['sumidouros']],
        "edges": [
            {
                "from": mapa_nome_para_indice[r['origem']],
                "to": mapa_nome_para_indice[r['destino']],
                "capacity": r['capacidade']
            } for r in rede_usuario['rotas']
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            print(f"Enviando para API do Dev2: {payload_para_dev2}")
            response = await client.post(DEV2_FLUXO_API_URL, json=payload_para_dev2, timeout=20.0)
            response.raise_for_status()
            resultado_dev2 = response.json()
            print(f"Recebido da API do Dev2: {resultado_dev2}")

    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Erro ao comunicar com a API de cálculo de fluxo (Dev2): {exc}. A API  pode estar offline ou com problemas.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro inesperado: {e}")

    mapa_indice_para_nome = {i: nome for nome, i in mapa_nome_para_indice.items()}

    resultado_final_formatado = {
        "fluxo_maximo": resultado_dev2.get("maxFlow"),
        "rotas_com_fluxo": [
            {
                "origem": mapa_indice_para_nome.get(edge.get("from")),
                "destino": mapa_indice_para_nome.get(edge.get("to")),
                "capacidade": edge.get("capacity"),
                "fluxo": edge.get("flow")
            } for edge in resultado_dev2.get("edges", [])
        ]
    }

    db["resultado_fluxo"] = resultado_final_formatado
    return resultado_final_formatado


@app.get("/resultados")
def obter_resultados():
    """
    Endpoint para que o frontend (Dev 3) possa buscar os resultados
    do cálculo de fluxo de forma já formatada.
    """
    resultado = db.get("resultado_fluxo")
    if not resultado:
        raise HTTPException(status_code=404, detail="Nenhum cálculo de fluxo foi realizado.")
    
    return {
        "rede_configurada": db.get("rede_formatada_usuario"),
        "analise_fluxo": resultado
    }