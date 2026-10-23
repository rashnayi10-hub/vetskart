import tempfile
import unittest
from pathlib import Path
from src.pipeline import assign_requests, km_between, run, validate_requests

ROOT = Path(__file__).resolve().parents[1]

class PipelineTests(unittest.TestCase):
    def test_distance_same_location(self):
        self.assertAlmostEqual(km_between(12.97, 77.59, 12.97, 77.59), 0)

    def test_invalid_coordinates_rejected(self):
        valid, rejected = validate_requests([{'request_id':'R','pet_name':'X','service_type':'consultation','latitude':'200','longitude':'1','requested_at':'2026-10-20T00:00:00Z'}])
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(rejected), 1)

    def test_no_double_booking(self):
        reqs = [dict(request_id=k, requested_at='2026-10-20T00:00:00+00:00', service_type='consultation', latitude=0, longitude=0) for k in ('A','B')]
        vets = [dict(vet_id='V1', available=True, services={'consultation'}, latitude=0, longitude=0, service_radius_km=10)]
        self.assertEqual([a['status'] for a in assign_requests(reqs, vets)], ['assigned', 'unassigned'])

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            report = run(ROOT / 'data', Path(d))
            self.assertEqual(report['requests_received'], 6)
            self.assertEqual(report['invalid_requests'], 1)
            self.assertEqual(report['assigned'], 3)
            self.assertTrue((Path(d) / 'petcare.db').exists())

if __name__ == '__main__':
    unittest.main()
