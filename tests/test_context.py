import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from backend.context import (DIGEST_INSTRUCTION, batches, compact_context,
                             context_limit, estimate_tokens, split_text, read_digest)
from backend.main import app, restore_summary, SavedEvent


def final_report():
    return {'recommendation': '建议先进行有预算上限和明确验收指标的小规模试点，关键缺口确认后再扩大。',
            'alternatives': '保留低成本方案，暂缓未经验证的高投入方案。',
            'execution_steps': [{'action': '实施一个受控的小规模试点', 'owner': '项目负责人',
                'timing': '第一周，估算', 'deliverable': '可复核试点报告', 'acceptance': '原始数据齐全并达到用户确认的阈值'}],
            'budget': '预算按用户上限控制，未提供单价的项目待核实。',
            'pilot': '先用固定样本执行试点，再根据可复核数据决定是否继续。',
            'next_actions': ['确认预算上限', '收集原始样本', '确定可复核的验收阈值'],
            'risks': ['关键资料缺失时暂停扩大投入'], 'blocking_conditions': ['失败工单仍须补查'],
            'research_status': '仅找到搜索摘要线索，失败工单和来源索引见系统保留清单。'}


class ContextTests(unittest.IsolatedAsyncioTestCase):
    def test_plain_notes_and_legacy_json_but_not_broken_json(self):
        text = '预算上限1000元，期限14天，性能验证失败，必须保留不确定性。'
        self.assertEqual(read_digest(text), text)
        self.assertEqual(read_digest(json.dumps({'summary': text})), text)
        self.assertEqual(read_digest('[R2-A1-T1-S1] ' + text), '[R2-A1-T1-S1] ' + text)
        self.assertIsNone(read_digest('{"summary":"输出到一半'))
        self.assertIsNone(read_digest('<think>尚在思考，没有正文'))

    async def test_broken_notes_retry_plain_text_without_json_dependency(self):
        calls = []
        text = '预算上限1000元，期限14天，性能验证失败，必须保留不确定性。'
        async def summarize(group, instruction, schema, output_tokens):
            self.assertFalse(schema)
            calls.append(instruction)
            return '{"summary":"断裂' if len(calls) % 2 else text
        result = await compact_context([{'speaker': '用户', 'content': text * 600}],
                                       'gemma2:9b', '报告要求', 3600, summarize)
        self.assertGreaterEqual(len(calls), 2)
        self.assertIn(text, serialize_for_test(result))
        self.assertLessEqual(estimate_tokens(result, '报告要求', 3600), 8192)

    async def test_repeated_bad_notes_fall_back_to_labeled_original_excerpts(self):
        text = '预算1000元，期限14天。R2-A1-T2性能验证失败，禁止声称成功。'
        warnings = []
        result = await compact_context([{'speaker': '原始用户目标', 'content': text * 800}],
            'gemma2:9b', '报告要求', 3600, AsyncMock(return_value='{"summary":"断裂'), warnings=warnings)
        self.assertTrue(warnings)
        self.assertIn('原文摘录', serialize_for_test(result))
        self.assertIn('验证失败', serialize_for_test(result))
        self.assertLessEqual(estimate_tokens(result, '报告要求', 3600), 8192)

    async def test_small_context_unchanged_without_model_calls(self):
        messages = [{'speaker': '用户', 'content': '原始问题'}]
        summarize = AsyncMock()
        result = await compact_context(messages, 'gemma2:9b', 'prompt', 3600, summarize)
        self.assertEqual(result, messages)
        summarize.assert_not_awaited()

    async def test_long_unicode_project_is_batched_then_fits_gemma(self):
        messages = [{'speaker': f'顾问{i}', 'content': f'顾问{i}的独立方案；风险未验证。' * 2500} for i in range(8)]
        seen = []
        async def summarize(group, instruction, schema, output_tokens):
            self.assertLessEqual(estimate_tokens(group, instruction, output_tokens), 8192)
            seen.extend(m['speaker'] for m in group)
            return json.dumps({'summary': '保留顾问不同方案、用户预算、验收条件、失败工单及来源编号。' * 4}, ensure_ascii=False)
        result = await compact_context(messages, 'gemma2:9b', '最终报告要求', 3600, summarize)
        self.assertLessEqual(estimate_tokens(result, '最终报告要求', 3600), 8192)
        for i in range(8):
            self.assertIn(f'顾问{i}', seen)
        self.assertEqual(messages[0]['content'].count('顾问0'), 2500)

    def test_escaped_json_fragments_never_exceed_batch_budget(self):
        messages = [{'speaker': '长资料', 'content': '"\\\n中文' * 30000}]
        groups = list(batches(messages, 'gemma2:9b'))
        self.assertTrue(groups)
        self.assertTrue(all(estimate_tokens(g, DIGEST_INSTRUCTION, 900) <= 8192 for g in groups))
        self.assertEqual(''.join(m['content'] for g in groups for m in g), messages[0]['content'])

    def test_multibyte_splitting_preserves_every_character(self):
        text = '用户预算€100、来源R2-A1-T1-S1🙂' * 50
        pieces = list(split_text(text, 64))
        self.assertEqual(''.join(pieces), text)
        self.assertTrue(all(len(p.encode('utf-8')) <= 64 for p in pieces))


class SummaryRecoveryTests(unittest.TestCase):
    def test_summary_survives_broken_compression_and_discloses_degradation(self):
        def handle(request):
            if request.url.path == '/api/version':
                return httpx.Response(200, json={'version': '0.40.9'})
            if request.url.path == '/api/tags':
                return httpx.Response(200, json={'models': [{'name': 'gemma2:9b'}]})
            payload = json.loads(request.content)
            system = payload['messages'][0]['content']
            value = '{"summary":"不完整' if '资料压缩员' in system else json.dumps(final_report(), ensure_ascii=False)
            return httpx.Response(200, json={'message': {'content': value}})
        original = httpx.AsyncClient
        def factory(**kwargs):
            return original(transport=httpx.MockTransport(handle), **kwargs)
        messages = [{'type': 'user', 'content': '预算1000元，期限14天。'},
                    {'type': 'message', 'speaker': '顾问', 'round': 2,
                     'content': '性能验证失败，不得声称通过。' * 3000}]
        with patch('backend.main.httpx.AsyncClient', side_effect=factory):
            response = TestClient(app).post('/api/summarize', json={'moderator': 'gemma2:9b', 'messages': messages})
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(events[-1]['type'], 'done')
        summary = next(e for e in events if e['type'] == 'summary')
        self.assertIn('输入资料覆盖说明', summary['content'])
        self.assertIn('有损原文摘录', summary['content'])

    def test_retry_long_saved_project_without_rerunning_discussion_or_search(self):
        chats = []
        def handle(request):
            if request.url.path == '/api/version':
                return httpx.Response(200, json={'version': '0.40.9'})
            if request.url.path == '/api/tags':
                return httpx.Response(200, json={'models': [{'name': 'gemma2:9b'}]})
            payload = json.loads(request.content)
            chats.append(payload)
            self.assertEqual(payload['options']['num_ctx'], 8192)
            instruction = payload['messages'][0]['content']
            messages = json.loads(payload['messages'][1]['content'])
            self.assertLessEqual(estimate_tokens(messages, instruction, payload['options']['num_predict']), 8192)
            if '资料压缩员' in instruction:
                result = {'summary': '用户预算上限100元、期限7天。两位顾问方案不同，应先试点再扩大。R2-A1-T2检索失败，不能当作已核实。'}
            else:
                self.assertIn('咨询项目的负责人', instruction)
                result = final_report()
            return httpx.Response(200, json={'message': {'content': json.dumps(result, ensure_ascii=False)}})
        original = httpx.AsyncClient
        def factory(**kwargs):
            return original(transport=httpx.MockTransport(handle), **kwargs)
        messages = [
            {'type': 'user', 'speaker': '用户', 'content': '预算100元，期限7天，先输出试点方案。'},
            {'type': 'message', 'speaker': 'alpha', 'round': 1, 'content': '原始方案',
             'proposal': {'proposal': '具体独立方案和不同决策。' * 4000}},
            {'type': 'message', 'speaker': 'beta', 'round': 2, 'content': '修订方案',
             'proposal': {'proposal': '本轮方案，风险尚未验证。' * 4000}},
            {'type': 'research', 'speaker': '研究员', 'target': 'beta', 'round': 2,
             'content': '详细研究记录与反证。' * 5000,
             'sources': [{'id': 'R2-A1-T1-S1', 'title': '原始官方来源', 'url': 'https://example.com/official'}],
             'deliveries': [{'id': 'R2-A1-T2', 'consultant': 'beta', 'query': '具体未完成的成本验证',
                             'status': 'failed', 'sources': [], 'finding': 'rate limited'}]},
        ]
        with patch('backend.main.httpx.AsyncClient', side_effect=factory), \
             patch('backend.main.search_web', new=AsyncMock()) as search:
            response = TestClient(app).post('/api/summarize', json={'moderator': 'gemma2:9b', 'messages': messages})
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line) for line in response.text.splitlines()]
        search.assert_not_awaited()
        self.assertGreater(len(chats), 1)
        self.assertEqual(events[0]['phase'], 'summary_compact')
        summary = next(e for e in events if e['type'] == 'summary')
        self.assertIn('R2-A1-T2', summary['content'])
        self.assertIn('具体未完成的成本验证', summary['content'])
        self.assertIn('https://example.com/official', summary['content'])
        self.assertEqual(summary['open_tasks'], 1)
        self.assertEqual(events[-1]['type'], 'done')

    def test_restore_uses_only_latest_project_evidence(self):
        messages = [SavedEvent(type='user', content='旧项目'),
                    SavedEvent(type='research', sources=[{'id': 'old', 'url': 'https://old.example'}]),
                    SavedEvent(type='user', content='新项目'),
                    SavedEvent(type='message', speaker='alpha', content='新方案', round=1)]
        _, sources, _, _ = restore_summary(messages)
        self.assertEqual(sources, [])

    def test_retry_requires_existing_proposals(self):
        response = TestClient(app).post('/api/summarize', json={
            'moderator': 'gemma2:9b', 'messages': [{'type': 'user', 'content': '尚无方案'}]})
        self.assertEqual(response.status_code, 422)


def serialize_for_test(value):
    return json.dumps(value, ensure_ascii=False)
