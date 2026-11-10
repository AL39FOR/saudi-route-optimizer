"""V13 regression tests for ordered multistop trips and academic matching."""
import unittest
from pathlib import Path
import networkx as nx
from core import graph_for_leg, make_graph, k_trips_sensible
from optimization_model import solve_shortest_path_model
HERE=Path(__file__).resolve().parent
EXCLUDED={'L034','L044','L052','L055'}

class OrderedStopsTests(unittest.TestCase):
    def setUp(self):
        self.g=nx.DiGraph()
        self.g.add_edge('A','D',distance_km=1,duration_min=1)
        self.g.add_edge('D','B',distance_km=1,duration_min=1)
        self.g.add_edge('A','C',distance_km=3,duration_min=3)
        self.g.add_edge('C','B',distance_km=3,duration_min=3)
        self.g.add_edge('B','D',distance_km=4,duration_min=4)

    def test_early_future_stop_blocked(self):
        flexible=k_trips_sensible(self.g,['A','B','D'],k=1, enforce_stop_order=False)[0]
        strict=k_trips_sensible(self.g,['A','B','D'],k=1, enforce_stop_order=True)[0]
        self.assertEqual(flexible.legs[0].cities,('A','D','B'))
        self.assertEqual(strict.legs[0].cities,('A','C','B'))
        self.assertAlmostEqual(strict.km,10)

    def test_strict_does_not_mutate_network(self):
        edges=set(self.g.edges())
        part=graph_for_leg(self.g,['A','B','D'],0,enforce_stop_order=True)
        self.assertNotIn('D',part)
        self.assertEqual(set(self.g.edges()),edges)
        self.assertIn('D',self.g)

    def test_no_feasible_stage_strict(self):
        g=nx.DiGraph()
        g.add_edge('A','D',distance_km=1,duration_min=1)
        g.add_edge('D','B',distance_km=1,duration_min=1)
        g.add_edge('B','D',distance_km=1,duration_min=1)
        self.assertEqual(k_trips_sensible(g,['A','B','D'],enforce_stop_order=True),[])
        self.assertTrue(k_trips_sensible(g,['A','B','D'],enforce_stop_order=False))

    def test_two_cities_unchanged(self):
        for metric in ('distance_km','duration_min'):
            flexible=k_trips_sensible(self.g,['A','D'],metric=metric,enforce_stop_order=False)
            strict=k_trips_sensible(self.g,['A','D'],metric=metric,enforce_stop_order=True)
            self.assertEqual([(t.km,t.minutes) for t in flexible],[(t.km,t.minutes) for t in strict])

    def test_real_trip_needs_reviewed_corridor(self):
        ordered=['الخبر','أبها','الرياض']
        g=make_graph(HERE/'road_distances_osrm.csv',excluded_link_ids=EXCLUDED|{'L068'})
        self.assertEqual(k_trips_sensible(g,ordered,enforce_stop_order=True),[])
        loose=k_trips_sensible(g,ordered,enforce_stop_order=False)
        self.assertTrue(loose)
        self.assertIn('الرياض',loose[0].legs[0].cities[1:-1])
        g2=make_graph(HERE/'road_distances_osrm.csv',excluded_link_ids=EXCLUDED)
        strict=k_trips_sensible(g2,ordered,enforce_stop_order=True)
        self.assertTrue(strict)
        self.assertNotIn('الرياض',strict[0].legs[0].cities)
        self.assertEqual(strict[0].legs[1].end,'الرياض')
        self.assertGreater(strict[0].km,loose[0].km)

    def test_academic_solution_matches_stage_limited_route(self):
        g=make_graph(HERE/'road_distances_osrm.csv',excluded_link_ids=EXCLUDED)
        stops=['الخبر','أبها','الرياض']
        for metric in ('distance_km','duration_min'):
            trips=k_trips_sensible(g,stops,enforce_stop_order=True,metric=metric)
            self.assertTrue(trips)
            for i,leg in enumerate(trips[0].legs):
                stage_graph=graph_for_leg(g,stops,i,enforce_stop_order=True)
                model=solve_shortest_path_model(stage_graph,leg.start,leg.end,metric)
                self.assertEqual(model.path,leg.cities)
                self.assertAlmostEqual(model.objective_value,leg.km if metric=='distance_km' else leg.minutes,places=2)
                self.assertEqual(model.largest_balance_error,0)

    def test_single_stage_stays_975(self):
        g=make_graph(HERE/'road_distances_osrm.csv',excluded_link_ids=EXCLUDED|{'L068'})
        route=k_trips_sensible(g,['الرياض','أبها'],metric='distance_km',enforce_stop_order=True)[0]
        self.assertAlmostEqual(route.km,975.341,places=2)

    def test_app_contains_strict_option(self):
        app=(HERE/'app.py').read_text(encoding='utf-8')
        self.assertIn('احترام ترتيب المحطات',app)
        self.assertIn('stage_graph',app)
        self.assertIn('highlighted_dataframe',app)

if __name__=='__main__':
    unittest.main()
