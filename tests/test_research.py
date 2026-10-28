import unittest
from backend.research import parse_queries, normalize_results


class ResearchTests(unittest.TestCase):
    def test_query_fallback_and_bounds(self):
        self.assertEqual(parse_queries('not json', '原始问题'), ['原始问题'])
        self.assertEqual(parse_queries('[" A ","A",5,"B","C","D"]', 'question'), ['A', 'B', 'C'])

    def test_filter_unsafe_links_deduplicate_and_limit(self):
        rows = [{'href': 'javascript:alert(1)'}, {'href': 'file:///C:/secret'},
                {'href': 'https://user:password@example.com'}]
        rows += [{'href': f'https://example.com/{n}', 'body': 'x' * 1000} for n in range(8)]
        rows += [rows[3]]
        results = normalize_results(rows)
        self.assertEqual(len(results), 6)
        self.assertEqual([r['id'] for r in results], list(range(1, 7)))
        self.assertTrue(all(len(r['snippet']) == 700 for r in results))
