import json
import unittest
from unittest.mock import patch, AsyncMock

import httpx
from fastapi.testclient import TestClient

from backend.main import app, answer, resolve_ollama


class OllamaCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_alternative_service_when_default_is_stopped(self):
        def handle(request):
            if request.url.port == 11434:
                raise httpx.ConnectError('stopped', request=request)
            return httpx.Response(200, json={'version':'0.40.9'} if request.url.path=='/api/version' else {'models':[{'name':'qwen3.5:9b'}]})
        with patch.dict('os.environ', {}, clear=True):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                self.assertEqual(await resolve_ollama(client),'http://127.0.0.1:11435')

    async def test_old_service_switches_only_with_same_models(self):
        def handle(request):
            if request.url.path == '/api/version':
                return httpx.Response(200, json={'version': '0.5.13' if request.url.port == 11434 else '0.40.9'})
            return httpx.Response(200, json={'models': [{'name': 'deepseek-r1:8b'}]})
        with patch.dict('os.environ', {}, clear=True):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                self.assertEqual(await resolve_ollama(client), 'http://127.0.0.1:11435')

    async def test_does_not_switch_if_models_are_missing(self):
        def handle(request):
            if request.url.path == '/api/version':
                return httpx.Response(200, json={'version': '0.5.13' if request.url.port == 11434 else '0.40.9'})
            return httpx.Response(200, json={'models': [{'name': 'deepseek-r1:8b'}] if request.url.port == 11434 else []})
        with patch.dict('os.environ', {}, clear=True):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                self.assertEqual(await resolve_ollama(client), 'http://127.0.0.1:11434')

    async def test_readable_unsupported_model_error(self):
        def handle(request):
            return httpx.Response(500, json={'error': 'this model is not supported by your version of Ollama. You may need to upgrade'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with self.assertRaisesRegex(ValueError, '版本不支持'):
                await answer(client, 'deepseek-r1:8b', [], 'test')


class DiscussionTests(unittest.TestCase):
    def run_discussion(self, failed=(), rounds=2, history=None, web_search=True, malformed=False):
        calls = []
        versions = {}
        def handle(request):
            if request.url.path == '/api/tags':
                return httpx.Response(200, json={'models': [{'name': 'alpha'}, {'name': 'beta'}]})
            payload = json.loads(request.content)
            calls.append(payload)
            model = payload['model']
            if model in failed:
                return httpx.Response(500, json={'error': 'not enough memory'})
            system = payload['messages'][0]['content']
            if '你是咨询项目的一位独立顾问' in system:
                versions[model] = versions.get(model, 0) + 1
                version = versions[model]
                data = {
                    'proposal': f'{model} 第{version}版方案：先实施小规模验证，再根据指标决定是否扩大投入。',
                    'execution_steps': [{'action': '执行一个可复现的验证步骤', 'owner': '项目负责人',
                        'timing': '第一周，依据试点范围估算', 'deliverable': '试点报告', 'acceptance': '输出可复核的数据记录'}],
                    'budget': '预算尚未确定，需查官方价格并基于工作量估算。',
                    'risks': ['供应商限制；先做小规模验证'], 'assumptions': ['用户尚未给出预算'],
                    'changes': f'第{version}版，明确比较证据后修订方案。',
                    'research_tasks': [{'query': f'{model} v{version} official pricing',
                        'purpose': '验证本方案的成本假设', 'decision': '如超预算则改用替代路线',
                        'expected_source': '官方价格页面', 'priority': 'high'}]}
                if malformed:
                    data.pop('research_tasks')
                result = json.dumps(data, ensure_ascii=False)
            elif '你是咨询项目的负责人' in system:
                data = {'recommendation': '基于已提供线索提出有条件的试点方案，尚需确认用户预算和地区。',
                    'alternatives': '比较两位顾问方案，优先选择验证成本较低者。',
                    'execution_steps': [{'action': '执行一个可复现的验证步骤', 'owner': '项目负责人',
                        'timing': '第一周，估算', 'deliverable': '试点报告', 'acceptance': '具备可检查的原始数据'}],
                    'budget': '预算待确认，所有数字均需注明依据。', 'pilot': '先完成小规模试点，用用户认可的指标决定是否扩大。',
                    'next_actions': ['确认预算', '选择试点范围', '定义验收指标'],
                    'risks': ['验证失败时停止投入'], 'blocking_conditions': ['预算和地区待确认'],
                    'research_status': '仅找到搜索摘要线索，尚未核验网页全文。'}
                result = json.dumps(data, ensure_ascii=False)
            else:
                result = '研究员交付：仅搜索摘要线索，未核验全文。'
            return httpx.Response(200, json={'message': {'content': result}})
        original = httpx.AsyncClient
        def factory(**kwargs):
            return original(transport=httpx.MockTransport(handle), **kwargs)
        with patch('backend.main.httpx.AsyncClient', side_effect=factory):
            response = TestClient(app).post('/api/discuss', json={
                'models': ['alpha', 'beta'], 'moderator': 'alpha', 'rounds': rounds,
                'question': '如何实施一个可验收的项目？', 'web_search': web_search, 'researcher': 'beta',
                'history': history if history is not None else [{'speaker': '用户', 'content': '此前用户背景'}]})
        self.assertEqual(response.status_code, 200)
        return calls, [json.loads(line) for line in response.text.splitlines()]

    @staticmethod
    def sources():
        return [{'id': 1, 'title': 'Official', 'url': 'https://example.com/docs', 'snippet': '原始资料及待核实的价格线索'}]

    def test_proposals_then_research_for_every_consultant_every_round(self):
        with patch('backend.main.search_web', new=AsyncMock(return_value=self.sources())) as search:
            calls, events = self.run_discussion()
        self.assertEqual(search.await_count, 4)
        queries = [call.args[0][0] for call in search.await_args_list]
        self.assertEqual(queries, ['alpha v1 official pricing', 'beta v1 official pricing',
                                  'alpha v2 official pricing', 'beta v2 official pricing'])
        messages = [e for e in events if e['type'] == 'message']
        self.assertEqual([e['round'] for e in messages], [1, 1, 2, 2])
        self.assertTrue(all(e['tasks'] and e['proposal']['execution_steps'] for e in messages))
        significant = [(e['type'], e.get('round')) for e in events if e['type'] in ('message', 'research', 'summary')]
        self.assertEqual(significant, [('message', 1), ('message', 1), ('research', 1), ('research', 1),
                                     ('message', 2), ('message', 2), ('research', 2), ('research', 2), ('summary', None)])
        proposal_calls = [c for c in calls if '你是咨询项目的一位独立顾问' in c['messages'][0]['content']]
        contexts = [json.loads(c['messages'][1]['content']) for c in proposal_calls]
        self.assertEqual(contexts[0], contexts[1])
        self.assertTrue(all(m['speaker'] == '用户' for m in contexts[0]))
        self.assertEqual(contexts[2], contexts[3])
        self.assertIn('R1-A1-T1-S1', proposal_calls[2]['messages'][1]['content'])
        self.assertIn('R1-A2-T1-S1', proposal_calls[2]['messages'][1]['content'])
        self.assertNotIn('alpha 第2版方案', proposal_calls[3]['messages'][1]['content'])
        self.assertIn('R2-A2-T1-S1', calls[-1]['messages'][1]['content'])
        self.assertEqual(events[-1]['type'], 'done')

    def test_source_ids_and_task_attribution_are_unique(self):
        with patch('backend.main.search_web', new=AsyncMock(return_value=self.sources())):
            _, events = self.run_discussion()
        reports = [e for e in events if e['type'] == 'research']
        ids = [s['id'] for e in reports for s in e['sources']]
        self.assertEqual(len(ids), len(set(ids)))
        for report in reports:
            for delivery in report['deliveries']:
                self.assertEqual(delivery['consultant'], report['target'])
                self.assertEqual(delivery['round'], report['round'])
                self.assertEqual(delivery['status'], 'found')

    def test_old_ai_answers_do_not_influence_independent_stage(self):
        calls, _ = self.run_discussion(web_search=False, history=[
            {'speaker': '用户', 'content': '原始用户目标'}, {'speaker': 'alpha', 'content': '不应泄露的旧方案'}])
        for call in calls[:2]:
            context = json.loads(call['messages'][1]['content'])
            self.assertEqual([m['speaker'] for m in context], ['用户', '用户'])
            self.assertNotIn('不应泄露', call['messages'][1]['content'])

    def test_failed_research_stays_unresolved_in_final(self):
        with patch('backend.main.search_web', new=AsyncMock(side_effect=ValueError('rate limited'))):
            calls, events = self.run_discussion()
        results = [e['task'] for e in events if e['type'] == 'task_result']
        self.assertEqual(len(results), 4)
        self.assertTrue(all(t['status'] == 'failed' and not t['sources'] for t in results))
        summary = next(e for e in events if e['type'] == 'summary')
        self.assertEqual(summary['open_tasks'], 4)
        self.assertIn('rate limited', calls[-1]['messages'][1]['content'])
        self.assertEqual(events[-1]['type'], 'done')

    def test_offline_keeps_unexecuted_work_orders(self):
        with patch('backend.main.search_web', new=AsyncMock()) as search:
            _, events = self.run_discussion(web_search=False)
        search.assert_not_awaited()
        self.assertTrue(all(e['task']['status'] == 'disabled' for e in events if e['type'] == 'task_result'))
        summary = next(e for e in events if e['type'] == 'summary')
        for heading in ('执行计划', '验收标准', '预算', '三项动作', '阻塞条件'):
            self.assertIn(heading, summary['content'])

    def test_invalid_proposals_do_not_trigger_generic_search(self):
        with patch('backend.main.search_web', new=AsyncMock()) as search:
            calls, events = self.run_discussion(malformed=True)
        self.assertEqual(len(calls), 4)  # One repair per consultant.
        search.assert_not_awaited()
        self.assertEqual(events[-1]['type'], 'error')
        self.assertNotIn('summary', [e['type'] for e in events])

    def test_failed_member_does_not_block_remaining_consultant(self):
        _, events = self.run_discussion(failed=('beta',), web_search=False)
        self.assertEqual(sum(e['type'] == 'model_error' for e in events), 2)
        self.assertIn('summary', [e['type'] for e in events])

    def test_all_failed_stops_without_summary(self):
        _, events = self.run_discussion(failed=('alpha', 'beta'), web_search=False)
        self.assertEqual(events[-1]['type'], 'error')
        self.assertNotIn('summary', [e['type'] for e in events])

    def test_at_least_two_rounds_required(self):
        response = TestClient(app).post('/api/discuss', json={
            'models': ['alpha'], 'moderator': 'alpha', 'question': 'test', 'rounds': 1})
        self.assertEqual(response.status_code, 422)

    def test_invalid_moderator(self):
        response = TestClient(app).post('/api/discuss', json={
            'models': ['alpha'], 'moderator': 'beta', 'question': 'test'})
        self.assertEqual(response.status_code, 422)


if __name__ == '__main__':
    unittest.main()
