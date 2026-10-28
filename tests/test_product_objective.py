import json
import unittest

from backend.workflow.engine import Run, WorkflowEngine
from backend.workflow.models import WorkflowRequest
from backend.workflow.objective import product_discovery


class ProductObjectiveTests(unittest.IsolatedAsyncioTestCase):
    def test_discovery_is_separate_from_implementation(self):
        self.assertTrue(product_discovery('我是app开发员，想开发一款能赚钱的app，卖点是什么'))
        self.assertFalse(product_discovery('给现有app设计数据库和部署架构'))
        self.assertFalse(product_discovery('帮我写一个女装视频脚本'))

    async def test_five_feedback_cycles_keep_product_delivery_and_independent_proposals(self):
        calls = []
        async def llm(client, model, context, instruction, url, **options):
            if 'questions' in (options.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            if 'verdict' in (options.get('structured') or {}).get('properties', {}):
                return json.dumps({'verdict':'pass','issues':[],'evidence_gaps':['竞争差异待验证'],
                                   'decision':'insufficient_evidence','decision_summary':'产品推荐与具体使用场景及卖点','decision_changed':True})
            calls.append((list(context), instruction))
            if options.get('structured'):
                return json.dumps({'answer': '具体产品候选及使用场景', 'research_tasks': []})
            if '产品选择交付' in instruction:
                return f'产品推荐第{run.cycle}版：做什么、为什么、卖点及使用例子'
            if '模拟客户反馈' in instruction:
                return '用户仍没有换用理由，需要重选产品方向，不能只补架构'
            return '产品比较与需求简报'

        body = WorkflowRequest(
            goal='我想开发一款面向15到30岁年轻人、能赚钱的app。做什么，为什么，卖点是什么？',
            depth='decision',
            agents=[{'id': a, 'name': a, 'model': a, 'role': '软件架构专家'} for a in ['a', 'b']],
            steps=[
                {'id': 'p', 'title': '需求', 'kind': 'personas', 'agent_ids': ['a']},
                {'id': 'd', 'title': '讨论', 'kind': 'discussion', 'agent_ids': ['a', 'b'], 'rounds': 1},
                {'id': 's', 'title': '交付', 'kind': 'summary', 'agent_ids': ['a']},
                {'id': 'f', 'title': '反馈', 'kind': 'feedback', 'agent_ids': []},
            ],
            optimization={'enabled': True, 'rounds': 5, 'persona_count': 1, 'personas': [
                {'id': 'u', 'name': '学生用户', 'agent_id': 'b', 'profile': '模拟学生，支付能力未知，不了解技术架构'}]},
        )
        run = Run(body, 'http://localhost:11434')
        await WorkflowEngine(llm, None).execute(run)
        self.assertEqual(run.state, 'completed')
        versions = [e['content'] for e in run.events if e['type'] == 'version']
        self.assertEqual(len(versions), 6)
        self.assertTrue(all(v.startswith('产品推荐') and '执行交付' not in v for v in versions))
        self.assertEqual(len([e for e in run.events if e.get('kind') == 'analysis']), 6)
        deliveries = [(c, i) for c, i in calls if '产品选择交付' in i]
        self.assertEqual(len(deliveries), 6)
        self.assertTrue(all('成员的技术专长不能改变这个任务' in i for _, i in deliveries))
        self.assertNotIn('本次任务的交付契约：产品机会选择', calls[0][1])
        self.assertIn('需要重选产品方向', str(deliveries[-1][0]))
        discussions = [c for c, i in calls if 'research_tasks' in i]
        for index in range(0, len(discussions), 2):
            self.assertEqual(discussions[index], discussions[index + 1])
        reviews = [i for _, i in calls if '模拟客户反馈' in i]
        self.assertTrue(all('产品用户评审重点' in i and '重点检验预算明细加总' not in i for i in reviews))
