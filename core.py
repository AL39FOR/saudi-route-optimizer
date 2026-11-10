"""Pure routing / optimization logic for an extensible Saudi city network.

Distances are supplied by data files, never estimated in this module.
Only network edges with OSRM measurements are included; missing values stay absent.
"""
from __future__ import annotations
import csv
import heapq
import itertools
import json
from dataclasses import dataclass
from pathlib import Path

import networkx as nx


@dataclass(frozen=True)
class Leg:
    start: str
    end: str
    cities: tuple[str, ...]
    km: float
    minutes: float


@dataclass(frozen=True)
class Trip:
    legs: tuple[Leg, ...]
    km: float
    minutes: float


def all_selected_cities(candidate_csv: str | Path) -> list[str]:
    with open(candidate_csv, encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        names = {name for row in r for name in (row['from_ar'], row['to_ar'])}
    names.discard('الرين')  # internal intersection, not a destination in the 29-city list
    return sorted(names)


def make_graph(measured_csv: str | Path, *, approved_only: bool = False, excluded_link_ids: set[str] | None = None) -> nx.DiGraph:
    g = nx.DiGraph()
    p = Path(measured_csv)
    if not p.exists():
        return g
    excluded_link_ids = excluded_link_ids or set()
    with p.open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            if r.get('link_id') in excluded_link_ids:
                continue
            if r.get('route_status') != 'ROUTED_UNVERIFIED':
                continue
            if approved_only and r.get('approved', '').upper() != 'YES':
                continue
            try:
                km = float(r['distance_km'])
                mins = float(r['duration_min'])
            except (KeyError, ValueError, TypeError):
                continue
            if km <= 0 or mins <= 0:
                continue
            a, b = r.get('from_ar', ''), r.get('to_ar', '')
            if not a or not b or a == b:
                continue
            raw_geo = r.get('geometry_json', '[]')
            try:
                geo = json.loads(raw_geo)
                if not isinstance(geo, list):
                    geo = []
            except ValueError:
                geo = []
            g.add_edge(a, b, distance_km=km, duration_min=mins,
                       link_id=r.get('link_id', ''), geom=geo,
                       approved=r.get('approved', '').upper() == 'YES')
    return g


def k_legs(g: nx.DiGraph, origin: str, dest: str, k: int = 3, weight: str = 'distance_km') -> list[Leg]:
    if origin == dest:
        raise ValueError('مدينتا الانطلاق والوصول متطابقتان')
    if origin not in g or dest not in g:
        return []
    try:
        paths = itertools.islice(nx.shortest_simple_paths(g, origin, dest, weight=weight), k)
        out = []
        for path in paths:
            out.append(Leg(origin, dest, tuple(path),
                           sum(g[u][v]['distance_km'] for u, v in zip(path, path[1:])),
                           sum(g[u][v]['duration_min'] for u, v in zip(path, path[1:]))))
        return out
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


def graph_for_leg(g: nx.DiGraph, ordered_stops: list[str], leg_index: int,
                  *, enforce_stop_order: bool = False) -> nx.DiGraph:
    """Return the graph permitted for one ordered leg.

    With strict order enabled, future required destinations cannot be used as
    intermediate nodes before their scheduled stage. Origin/end nodes are
    retained even if a city occurs again later in the itinerary.
    The original graph and its measurements are never modified.
    """
    if not 0 <= leg_index < len(ordered_stops) - 1:
        raise ValueError('Invalid stage number')
    if not enforce_stop_order or len(ordered_stops) <= 2:
        return g
    origin, dest = ordered_stops[leg_index:leg_index + 2]
    blocked = set(ordered_stops[leg_index + 2:]) - {origin, dest}
    return g.subgraph(n for n in g.nodes if n not in blocked).copy()


def k_trips(g: nx.DiGraph, ordered_stops: list[str], *, k: int = 3,
            metric: str = 'distance_km', enforce_stop_order: bool = False) -> list[Trip]:
    """Ordered stops: origin -> optional stopovers -> final destination.

    Enumerate K-best leg combinations, not merely the per-leg shortest choices.
    Stops are mandatory and ordered, but city nodes may recur across *different*
    legs if the topology requires it. We reject consecutive duplicate stops.
    """
    if not (2 <= len(ordered_stops) <= 7):
        raise ValueError('اختر بداية ونهاية و0–5 محطات وسيطة')
    if any(a == b for a, b in zip(ordered_stops, ordered_stops[1:])):
        raise ValueError('لا تكرر نفس المدينة في مرحلتين متتاليتين')
    if metric not in ('distance_km', 'duration_min'):
        raise ValueError('Unknown metric')
    legs = []
    for leg_index, (a, b) in enumerate(zip(ordered_stops, ordered_stops[1:])):
        available_graph = graph_for_leg(g, ordered_stops, leg_index,
                                        enforce_stop_order=enforce_stop_order)
        alternatives = k_legs(available_graph, a, b, k=k, weight=metric)
        if not alternatives:
            return []
        legs.append(alternatives)
    # The K globally best combinations can be composed from the K best per leg.
    heap = []
    best = []
    initial = (0,) * len(legs)
    seen = {initial}

    def total(ix):
        selected = [legs[j][v] for j, v in enumerate(ix)]
        return sum((q.km if metric == 'distance_km' else q.minutes) for q in selected)

    heapq.heappush(heap, (total(initial), initial))
    while heap and len(best) < k:
        _, ix = heapq.heappop(heap)
        chosen = tuple(legs[j][v] for j, v in enumerate(ix))
        best.append(Trip(chosen, sum(a.km for a in chosen), sum(a.minutes for a in chosen)))
        for j in range(len(ix)):
            nxt = list(ix)
            nxt[j] += 1
            nxt = tuple(nxt)
            if nxt not in seen and nxt[j] < len(legs[j]):
                seen.add(nxt)
                heapq.heappush(heap, (total(nxt), nxt))
    return best



def k_trips_sensible(g: nx.DiGraph, ordered_stops: list[str], *, k: int = 3,
                     metric: str = 'distance_km', max_gap_km: float = 200,
                     candidates_to_check: int = 30,
                     enforce_stop_order: bool = False) -> list[Trip]:
    """Show 1–k useful routes; do not display wildly longer alternatives.

    Each additional route must be within max_gap_km *in absolute kilometers* of
    the primary route. This rule remains distance-based when ranking by time.
    Scan more than k candidates so legitimate alternatives are not accidentally
    hidden merely because one early time-optimized route is a long detour.
    """
    if max_gap_km < 0 or candidates_to_check < k:
        raise ValueError('Invalid alternative distance limit')
    candidates = k_trips(g, ordered_stops, k=candidates_to_check, metric=metric,
                         enforce_stop_order=enforce_stop_order)
    if not candidates:
        return []
    baseline = candidates[0].km
    shown = [candidates[0]]
    for trip in candidates[1:]:
        if abs(trip.km - baseline) <= max_gap_km + 1e-8:
            shown.append(trip)
            if len(shown) >= k:
                break
    return shown


def fmt_time(minutes: float) -> str:
    whole = int(round(minutes))
    return f'{whole // 60} س {whole % 60} د'
