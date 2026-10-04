import unittest
from unittest.mock import patch

import rivals
from agent.contracts import PROD_URL


class RivalPublicReads(unittest.TestCase):
    def test_analyst_never_loads_credentials(self):
        with patch('agent.client._load_env', side_effect=AssertionError('credentials')), \
             patch('agent.transport.public_get', return_value={'teams': []}) as get:
            self.assertEqual(rivals.get('/api/leaderboard'), {'teams': []})
        self.assertEqual(get.call_args.args[:2], (PROD_URL, '/api/leaderboard'))

    def test_private_or_write_route_rejected(self):
        for route in ('/api/me', '/api/offers', '/api/duels'):
            with self.assertRaises(ValueError):
                rivals.get(route)


if __name__ == '__main__':
    unittest.main()
