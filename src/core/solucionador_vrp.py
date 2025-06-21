from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import requests, time, os, json, hashlib

class SolucionadorVRP:
    def __init__(self, dados_problema: dict):
        self.dados = dados_problema
        self._nomes_locais = list(dados_problema['coordenadas'].keys())
        self._coordenadas = list(dados_problema['coordenadas'].values())
        self._deposito_idx = self._nomes_locais.index(dados_problema['nome_deposito'])
        
        nomes_locais_ordenados = sorted(self._nomes_locais)
        assinatura_problema = "".join(nomes_locais_ordenados)
        hash_problema = hashlib.md5(assinatura_problema.encode()).hexdigest()
        
        ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.cache_path_tempo = os.path.join(ROOT_DIR, 'data', f'matriz_tempo_{hash_problema}.json')
        self.cache_path_dist = os.path.join(ROOT_DIR, 'data', f'matriz_distancia_{hash_problema}.json')
        
        self.manager = None
        self.routing = None
        self.solution = None
        self.FATOR_CUSTO = 100 

    def _get_osrm_route_info(self, coord1, coord2):
        loc = f"{coord1[1]},{coord1[0]};{coord2[1]},{coord2[0]}"
        url = f"http://router.project-osrm.org/route/v1/driving/{loc}"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get('code') == 'Ok':
                return {"distancia": data['routes'][0]['distance'], "tempo": data['routes'][0]['duration']}
        except requests.exceptions.RequestException as e:
            print(f"  [AVISO] Falha ao consultar OSRM: {e}.")
        return None

    def _criar_matrizes(self):
        matrizes = {'tempo': {}, 'distancia': {}}
        for tipo in ['tempo', 'distancia']:
            cache_path = self.cache_path_tempo if tipo == 'tempo' else self.cache_path_dist
            if os.path.exists(cache_path):
                print(f"✅ Cache de {tipo} encontrado! Carregando...")
                with open(cache_path, 'r') as f:
                    matriz_str_keys = json.load(f)
                    matrizes[tipo] = {int(k): {int(i):j for i,j in v.items()} for k, v in matriz_str_keys.items()}
            else:
                print(f"🛠️  Cache de {tipo} não encontrado. Construindo com OSRM...")
                num_locais = len(self._coordenadas)
                matriz_temp = {}
                for i in range(num_locais):
                    matriz_temp[i] = {}
                    for j in range(num_locais):
                        if i == j: matriz_temp[i][j] = 0; continue
                        info = self._get_osrm_route_info(self._coordenadas[i], self._coordenadas[j])
                        matriz_temp[i][j] = int(info[tipo]) if info else 9999999
                        time.sleep(0.05)
                matrizes[tipo] = matriz_temp
                print(f"💾 Salvando cache de {tipo}...")
                with open(cache_path, 'w') as f:
                    json.dump(matrizes[tipo], f)
        return matrizes['tempo'], matrizes['distancia']

    def resolver(self):
        matriz_tempo, matriz_distancia = self._criar_matrizes()
        self.manager = pywrapcp.RoutingIndexManager(len(matriz_tempo), self.dados['num_veiculos'], self._deposito_idx)
        self.routing = pywrapcp.RoutingModel(self.manager)

        def custo_financeiro_callback(from_index, to_index):
            from_node = self.manager.IndexToNode(from_index)
            to_node = self.manager.IndexToNode(to_index)
            distancia_km = matriz_distancia.get(from_node, {}).get(to_node, 0) / 1000.0
            custo_distancia = self.dados.get('custo_km', 0) * distancia_km
            tempo_servico_seg = self.dados.get('tempo_servico', 0)
            tempo_viagem_seg = matriz_tempo.get(from_node, {}).get(to_node, 0)
            tempo_total_horas = (tempo_viagem_seg + tempo_servico_seg) / 3600.0
            custo_tempo = self.dados.get('custo_hora', 0) * tempo_total_horas
            custo_total = custo_distancia + custo_tempo
            return int(custo_total * self.FATOR_CUSTO)

        custo_callback_index = self.routing.RegisterTransitCallback(custo_financeiro_callback)
        self.routing.SetArcCostEvaluatorOfAllVehicles(custo_callback_index)

        penalidade_nao_prioritario = 10000 * self.FATOR_CUSTO
        prioridades = self.dados.get('prioridades', {})
        for i, nome_local in enumerate(self._nomes_locais):
            if i == self._deposito_idx: continue
            if prioridades.get(nome_local) != 1:
                self.routing.AddDisjunction([self.manager.NodeToIndex(i)], penalidade_nao_prioritario)
        
        def tempo_callback(from_index, to_index):
            from_node = self.manager.IndexToNode(from_index)
            to_node = self.manager.IndexToNode(to_index)
            return matriz_tempo.get(from_node, {}).get(to_node, 999999) + self.dados.get('tempo_servico', 0)
        
        transit_callback_index_tempo = self.routing.RegisterTransitCallback(tempo_callback)
        self.routing.AddDimension(transit_callback_index_tempo, 0, 24 * 3600, False, 'Tempo')
        time_dimension = self.routing.GetDimensionOrDie('Tempo')
        
        for nome_local, janela in self.dados.get('janelas_de_tempo', {}).items():
            if nome_local in self._nomes_locais:
                index = self.manager.NodeToIndex(self._nomes_locais.index(nome_local))
                time_dimension.CumulVar(index).SetRange(janela[0], janela[1])

        def demanda_callback(from_index):
            from_node = self.manager.IndexToNode(from_index)
            return self.dados['demandas'].get(self._nomes_locais[from_node], 0)
        demand_callback_index = self.routing.RegisterUnaryTransitCallback(demanda_callback)
        self.routing.AddDimensionWithVehicleCapacity(demand_callback_index, 0, [self.dados['capacidade_veiculo']] * self.dados['num_veiculos'], True, 'Capacidade')

        balancear_por = self.dados.get('balancear_carga_por')
        if balancear_por == 'tempo':
            print("⚖️ Aplicando balanceamento por TEMPO...")
            time_dimension.SetGlobalSpanCostCoefficient(100)
        elif balancear_por == 'distancia':
            print("⚖️ Aplicando balanceamento por DISTÂNCIA...")
            def distancia_callback(from_index, to_index):
                from_node = self.manager.IndexToNode(from_index)
                to_node = self.manager.IndexToNode(to_index)
                return matriz_distancia.get(from_node, {}).get(to_node, 0)
            
            dist_callback_index = self.routing.RegisterTransitCallback(distancia_callback)
            self.routing.AddDimension(dist_callback_index, 0, 1000000, True, 'Distancia')
            distancia_dimension = self.routing.GetDimensionOrDie('Distancia')
            distancia_dimension.SetGlobalSpanCostCoefficient(30)

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
        search_parameters.local_search_metaheuristic = (routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_parameters.time_limit.FromSeconds(30)
        
        self.solution = self.routing.SolveWithParameters(search_parameters)

        if self.solution:
            return self._formatar_solucao(matriz_distancia, matriz_tempo, time_dimension)
        return None

    def _formatar_solucao(self, matriz_distancia, matriz_tempo, time_dimension):
        rotas_otimizadas, distancia_total, custo_total_operacional = [], 0, 0.0
        for id_veiculo in range(self.dados['num_veiculos']):
            index = self.routing.Start(id_veiculo)
            rota_veiculo_pontos, carga_rota, distancia_rota, custo_rota = [], 0, 0, 0.0
            
            while not self.routing.IsEnd(index):
                node_index = self.manager.IndexToNode(index)
                nome_local = self._nomes_locais[node_index]
                carga_rota += self.dados['demandas'].get(nome_local, 0)
                tempo_chegada = self.solution.Min(time_dimension.CumulVar(index))
                rota_veiculo_pontos.append({"local": nome_local, "horario_chegada": f"{int(tempo_chegada//3600):02d}:{int((tempo_chegada%3600)//60):02d}"})
                
                previous_index = index
                index = self.solution.Value(self.routing.NextVar(index))

                if not self.routing.IsEnd(index):
                    from_node = self.manager.IndexToNode(previous_index)
                    to_node = self.manager.IndexToNode(index)
                    
                    dist_arco = matriz_distancia.get(from_node, {}).get(to_node, 0)
                    distancia_rota += dist_arco
                    
                    tempo_arco = matriz_tempo.get(from_node, {}).get(to_node, 0) + self.dados.get('tempo_servico', 0)
                    custo_arco = (dist_arco / 1000.0 * self.dados.get('custo_km', 0)) + \
                                 (tempo_arco / 3600.0 * self.dados.get('custo_hora', 0))
                    custo_rota += custo_arco
            
            if len(rota_veiculo_pontos) > 1:
                distancia_total += distancia_rota
                custo_total_operacional += custo_rota
                rotas_otimizadas.append({
                    'veiculo_id': id_veiculo + 1, 'rota': rota_veiculo_pontos,
                    'distancia_metros': int(distancia_rota), 'carga_total': carga_rota,
                    'custo_rota': custo_rota
                })
        
       
        return {
            'rotas_otimizadas': rotas_otimizadas,
            'distancia_total_metros': int(distancia_total),
            'custo_total': custo_total_operacional 
        }
