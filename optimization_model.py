"""Academic shortest-path min-cost flow model (Saudi Route Optimizer).

Every directed road record is a separate decision variable x_ij.
Minimize sum(weight_ij * x_ij), subject to outgoing - incoming = +1 at
origin, -1 at destination, 0 elsewhere, with 0 <= x_ij <= 1 integer.

Because this is a unit-flow network with integer supplies and capacities,
network simplex returns an integral solution; positive arc weights ensure no
extraneous cycles in an optimum. No route costs are invented here.
"""
from __future__ import annotations
from dataclasses import dataclass
import networkx as nx


@dataclass(frozen=True)
class FlowModelResult:
    origin: str
    destination: str
    metric: str
    nodes: int
    decision_variables: int
    balance_constraints: int
    path: tuple[str, ...]
    selected_arcs: tuple[tuple[str,str], ...]
    objective_value: float
    distance_km: float
    duration_min: float
    largest_balance_error: int
    solver: str = 'Network simplex (integral minimum-cost flow)'


def solve_shortest_path_model(graph: nx.DiGraph, origin: str, destination: str,
                              metric: str = 'distance_km') -> FlowModelResult:
    if metric not in ('distance_km','duration_min'):
        raise ValueError('Unknown objective. Use distance_km or duration_min.')
    if origin == destination:
        raise ValueError('Origin and destination must be different.')
    if origin not in graph or destination not in graph:
        raise ValueError('One or both cities are missing from the measured road network.')

    # Positive weights from audited-source snapshot. Scale to integers to
    # avoid the documented precision issues of network simplex with floats.
    flow_graph = nx.DiGraph()
    for node in graph.nodes:
        flow_graph.add_node(node, demand=(-1 if node == origin else
                                          1 if node == destination else 0))
    for u,v,d in graph.edges(data=True):
        val=float(d[metric])
        if val <= 0:
            raise ValueError('All road costs must be strictly positive.')
        weight=int(round(val * 1000))
        if weight <= 0:
            raise ValueError('Road cost too small to represent safely.')
        flow_graph.add_edge(u,v,capacity=1,weight=weight)

    try:
        _, flows = nx.network_simplex(flow_graph)
    except (nx.NetworkXUnfeasible,nx.NetworkXError) as ex:
        raise ValueError('No feasible path in the currently selected road network.') from ex

    selected={(u,v) for u in flow_graph for v,value in flows[u].items() if value > 0}
    outgoing={u:v for u,v in selected}
    path=[origin]
    cur=origin
    for _ in range(len(graph.nodes)):
        if cur == destination: break
        if cur not in outgoing: raise RuntimeError('The solver returned a discontinuous path.')
        cur=outgoing[cur]
        if cur in path: raise RuntimeError('Unexpected directed cycle in the flow solution.')
        path.append(cur)
    if path[-1] != destination or len(selected) != len(path)-1:
        raise RuntimeError('Solver flow is not a single simple route.')

    largest_error=0
    for n in graph.nodes:
        outgoing_flow=sum(flows[n].values())
        incoming_flow=sum(flows[u].get(n,0) for u in flow_graph.predecessors(n))
        rhs=1 if n == origin else -1 if n == destination else 0
        largest_error=max(largest_error,abs(outgoing_flow-incoming_flow-rhs))
    if largest_error: raise RuntimeError('Flow balance constraints were violated.')

    edges=tuple(zip(path,path[1:]))
    km=sum(graph[u][v]['distance_km'] for u,v in edges)
    mins=sum(graph[u][v]['duration_min'] for u,v in edges)
    return FlowModelResult(origin,destination,metric,len(graph.nodes),
                           graph.number_of_edges(),len(graph.nodes),
                           tuple(path),edges,km if metric=='distance_km' else mins,
                           km,mins,largest_error)


def decision_variable_table(graph: nx.DiGraph, result: FlowModelResult) -> list[dict]:
    """One row per mathematical variable, with selected x=1 or otherwise x=0."""
    selected=set(result.selected_arcs)
    return [{'المتغير':f'x{i:03d}', 'من':u, 'إلى':v,
             'المسافة (كم)':round(float(d['distance_km']),3),
             'الوقت (دقيقة)':round(float(d['duration_min']),2),
             'x':int((u,v) in selected)}
            for i,(u,v,d) in enumerate(graph.edges(data=True),1)]


def flow_balance_table(graph: nx.DiGraph, result: FlowModelResult) -> list[dict]:
    selected=set(result.selected_arcs)
    records=[]
    for node in graph.nodes:
        out=sum((node,v) in selected for v in graph.successors(node))
        inc=sum((u,node) in selected for u in graph.predecessors(node))
        rhs=1 if node==result.origin else -1 if node==result.destination else 0
        records.append({'العقدة':node,'التدفق الخارج':out,'التدفق الداخل':inc,
                        'الخارج − الداخل':out-inc,'القيد المطلوب':rhs,
                        'محقق':out-inc==rhs})
    return records
