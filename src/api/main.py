import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Tuple, Optional
import traceback

from src.core.solucionador_vrp import SolucionadorVRP

class Rota(BaseModel):
    origem: str
    destino: str
    capacidade: int = Field(gt=0)

class RedeDeEntrega(BaseModel):
    fontes: List[str]
    sumidouros: List[str]
    rotas: List[Rota]

class ProblemaVRP(BaseModel):
    coordenadas: Dict[str, Tuple[float, float]]
    demandas: Dict[str, int]
    num_veiculos: int = Field(gt=0)
    capacidade_veiculo: int = Field(gt=0)
    nome_deposito: str
    janelas_de_tempo: Optional[Dict[str, Tuple[int, int]]] = None
    tempo_servico: Optional[int] = 0
    custo_km: Optional[float] = 0.0
    custo_hora: Optional[float] = 0.0
    prioridades: Optional[Dict[str, int]] = None
    balancear_carga_por: Optional[str] = None

app = FastAPI(
    title="Delivery Routing Optimizer API",
    description="API para otimização de rotas, fluxo e balanceamento de carga.",
    version="2.3.0"
)

DEV2_FLUXO_API_URL = "https://fluxo-maximo-api.onrender.com/fluxo-maximo"
db: Dict[str, Any] = {"rede_formatada_usuario": None, "resultado_fluxo": None}

@app.post("/roteirizar", summary="Calcula as rotas otimizadas para uma frota de veículos")
async def roteirizar_entregas(problema: ProblemaVRP):
    try:
        for local, demanda in problema.demandas.items():
            if demanda > problema.capacidade_veiculo:
                raise HTTPException(status_code=400, detail=f"A demanda para '{local}' ({demanda}) excede a capacidade do veículo ({problema.capacidade_veiculo}).")
        solver = SolucionadorVRP(problema.dict())
        solucao = solver.resolver()
        if solucao: return solucao
        else: raise HTTPException(status_code=400, detail="Não foi possível encontrar uma solução com os parâmetros fornecidos.")
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail={"message": "Ocorreu um erro crítico no servidor.", "traceback": traceback.format_exc()})

@app.post("/rede", summary="Configura uma rede para análise de fluxo")
def configurar_rede(rede: RedeDeEntrega):
    db["rede_formatada_usuario"] = rede.dict()
    db["resultado_fluxo"] = None
    return {"mensagem": f"Rede com {len(rede.rotas)} rotas configurada com sucesso."}

@app.post("/fluxo/calcular", summary="Dispara o cálculo de fluxo máximo (usando API externa)")
async def calcular_fluxo():
    rede_usuario = db.get("rede_formatada_usuario")
    if not rede_usuario: raise HTTPException(status_code=400, detail="Rede não configurada.")
    nodes = sorted(list(set([r['origem'] for r in rede_usuario['rotas']] + [r['destino'] for r in rede_usuario['rotas']] + rede_usuario['fontes'] + rede_usuario['sumidouros'])))
    mapa_nome_para_indice = {nome: i for i, nome in enumerate(nodes)}
    payload = {"nodeCount": len(nodes), "sources": [mapa_nome_para_indice[n] for n in rede_usuario['fontes']], "sinks": [mapa_nome_para_indice[n] for n in rede_usuario['sumidouros']], "edges": [{"from": mapa_nome_para_indice[r['origem']], "to": mapa_nome_para_indice[r['destino']], "capacity": r['capacidade']} for r in rede_usuario['rotas']]}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(DEV2_FLUXO_API_URL, json=payload, timeout=20.0)
            response.raise_for_status(); resultado_dev2 = response.json()
    except httpx.RequestError as exc: raise HTTPException(status_code=503, detail=f"Erro ao comunicar com API de fluxo: {exc}.")
    mapa_indice_para_nome = {i: nome for nome, i in mapa_nome_para_indice.items()}
    resultado_formatado = {"fluxo_maximo": resultado_dev2.get("maxFlow"), "rotas_com_fluxo": [{"origem": mapa_indice_para_nome.get(e.get("from")), "destino": mapa_indice_para_nome.get(e.get("to")), "capacidade": e.get("capacity"), "fluxo": e.get("flow")} for e in resultado_dev2.get("edges", [])]}
    db["resultado_fluxo"] = resultado_formatado
    return resultado_formatado

@app.get("/resultados", summary="Obtém os resultados da última análise de fluxo")
def obter_resultados():
    resultado = db.get("resultado_fluxo")
    if not resultado: raise HTTPException(status_code=404, detail="Nenhum cálculo de fluxo foi realizado.")
    return {"rede_configurada": db.get("rede_formatada_usuario"), "analise_fluxo": resultado}