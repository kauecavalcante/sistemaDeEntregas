import json
import networkx as nx 
# (dev 1 modelagem de dados)

class NoRede:
    """Classe base para qualquer nó na rede (depósito, hub, etc.)."""
    def __init__(self, id: str, nome: str, lat: float, lon: float):
        self.id = id
        self.nome = nome
        self.coordenadas = (lat, lon)

    def __repr__(self):
        return f"{self.__class__.__name__}(nome='{self.nome}')"

class Deposito(NoRede):
    """Representa um centro de distribuição, de onde os pacotes saem."""
    pass

class Hub(NoRede):
    """Representa um hub logístico intermediário."""
    pass

class ZonaEntrega(NoRede):
    """Representa um cliente final ou uma zona de entrega."""
    pass

class Rota:
    """Representa uma aresta do grafo, conectando dois nós com uma capacidade."""
    def __init__(self, origem: NoRede, destino: NoRede, capacidade: int):
        if capacidade < 0:
            raise ValueError("A capacidade da rota não pode ser negativa.")
        self.origem = origem
        self.destino = destino
        self.capacidade = capacidade
    
    def __repr__(self):
        return f"Rota(de='{self.origem.nome}', para='{self.destino.nome}', cap={self.capacidade})"

class RedeLogistica:
    """
    Classe principal que constrói e gerencia o grafo da rede logística.
    """
    def __init__(self):
        self.nos = {} 
        self.rotas = []

    def adicionar_no(self, no: NoRede):
        self.nos[no.nome] = no

    def adicionar_rota(self, nome_origem: str, nome_destino: str, capacidade: int):
        if nome_origem not in self.nos or nome_destino not in self.nos:
            raise KeyError("Nó de origem ou destino não encontrado na rede.")
        
        origem_no = self.nos[nome_origem]
        destino_no = self.nos[nome_destino]
        rota = Rota(origem_no, destino_no, capacidade)
        self.rotas.append(rota)

    @classmethod
    def carregar_de_json(cls, caminho_arquivo: str) -> 'RedeLogistica':
        """Cria uma instância da RedeLogistica a partir de um arquivo JSON."""
        print(f" Carregando dados da rede do arquivo: {caminho_arquivo}")
        
        rede = cls()
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)

        # Mapeamento de tipo para classe
        mapeamento_classes = {
            "deposito": Deposito,
            "hub": Hub,
            "zona": ZonaEntrega
        }

        # Criar e adicionar os nós
        for v in dados['vertices']:
            classe_no = mapeamento_classes.get(v['tipo'].lower())
            if not classe_no:
                raise ValueError(f"Tipo de vértice desconhecido: {v['tipo']}")
            
            no = classe_no(id=v['id'], nome=v['nome'], lat=v['lat'], lon=v['lon'])
            rede.adicionar_no(no)

        # Criar e adicionar as rotas
        for r in dados['rotas']:
            rede.adicionar_rota(r['origem'], r['destino'], r['capacidade'])
        
        print("✅ Rede carregada com sucesso.")
        return rede

    def validar_integridade(self) -> bool:
        """
        Valida a integridade da rede, verificando a conectividade.
        Retorna True se a rede for válida, senão lança uma exceção.
        """
        print("\n Executando validação de integridade da rede...")
        G = nx.DiGraph() 

        # Adiciona nós e arestas ao grafo networkx
        for nome in self.nos:
            G.add_node(nome)
        for rota in self.rotas:
            G.add_edge(rota.origem.nome, rota.destino.nome)

        # Verifica se existem nós
        if not self.nos:
            raise ValueError("Erro de integridade: A rede não possui nós.")
        
        # 2. Verifica se existem rotas
        if not self.rotas:
            print("Aviso: A rede não possui rotas.")
            return True

        
        if not nx.is_weakly_connected(G):
            componentes = list(nx.weakly_connected_components(G))
            raise ConnectionError(f"Erro de integridade: A rede não é conectada. Existem {len(componentes)} grupos de nós isolados.")
            
        print("✅ Integridade da rede validada com sucesso! A rede é conectada.")
        return True

    def para_dicionario_api(self) -> dict:
        """Converte a rede para o formato de dicionário esperado pela API do Dev 5."""
        fontes = [no.nome for no in self.nos.values() if isinstance(no, Deposito)]
        sumidouros = [no.nome for no in self.nos.values() if isinstance(no, ZonaEntrega)]
        
        rotas_dict = [
            {"origem": rota.origem.nome, "destino": rota.destino.nome, "capacidade": rota.capacidade}
            for rota in self.rotas
        ]

        return {
            "fontes": fontes,
            "sumidouros": sumidouros,
            "rotas": rotas_dict
        }