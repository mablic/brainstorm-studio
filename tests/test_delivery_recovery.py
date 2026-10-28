import json
import unittest
from pathlib import Path
from backend.workflow.quality import incomplete_output
from backend.workflow.engine import Run, WorkflowEngine
from backend.workflow.delivery import OfflineProduct
from test_quality_gates import body, PRODUCT, passed
from test_conclusion_regression import evidence_review


class DeliveryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_run_ends_with_concrete_structured_choice_and_evidence_boundary(self):
        product=OfflineProduct(product='本地临时记录工具',target_user='20到30岁的上班族',
            use_example='用户主动粘贴临时文字，点击保存，随后按日期查找并导出一份文本文件。',
            reason_hypotheses=['可能减少临时文字丢失。','系统备忘录不支持图片，填补空白。'],minimal_features=['粘贴保存','日期查找','导出'],
            excluded_features=['云同步','后台监听'],competitor_names_to_check=['系统备忘录','Joplin'],
            first_experiment='请五位目标用户记录三天，观察实际找回记录的次数；无人使用则放弃，这是暂定决策线。')
        async def llm(_,model,context,instruction,url,**options):
            props=(options.get('structured') or {}).get('properties',{})
            if 'questions' in props:return '{"questions":[]}'
            if 'verdict' in props:return passed()
            if 'competitor_names_to_check' in props:return product.model_dump_json()
            return PRODUCT
        run=Run(body(),'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        final=next(e for e in reversed(run.events) if e['type']=='deliverable')
        self.assertEqual(run.state,'completed')
        self.assertEqual(final['delivery_status'],'provisional')
        self.assertIn(product.product,final['content'])
        self.assertIn('竞争稀少这一要求尚未验证',final['content'])
        self.assertIn('Joplin',final['content'])
        self.assertNotIn('系统备忘录不支持图片',final['content'])

    def test_both_actual_complete_answers_with_mixed_quotes_are_accepted(self):
        samples=json.loads((Path(__file__).parent/'fixtures/mixed_quotes.json').read_text(encoding='utf-8'))
        self.assertEqual(len(samples),2)
        for sample in samples:
            self.assertIsNone(incomplete_output(sample))

    async def test_offline_proposal_does_not_repeat_impossible_research(self):
        calls=[]
        async def llm(_,model,context,instruction,url,**options):
            calls.append(instruction)
            if 'verdict' in (options.get('structured') or {}).get('properties',{}):
                return evidence_review().model_dump_json()
            return json.dumps({'answer':PRODUCT,'research_tasks':[]})
        run=Run(body(discussion=True),'http://localhost:11434')
        result=await WorkflowEngine(llm,None).checked_call(run,run.plan.agents[0],run.plan.steps[1],[],
            '生成独立建议','独立方案')
        self.assertIn(PRODUCT,json.loads(result)['answer'])
        self.assertEqual(len(calls),2)
        self.assertFalse(any(e['type']=='step_return' for e in run.events))

    async def test_successful_delivery_survives_later_review_outage(self):
        async def llm(_,model,context,instruction,url,**options):
            props=(options.get('structured') or {}).get('properties',{})
            if 'questions' in props:return '{"questions":[]}'
            if 'verdict' in props:return passed()
            if '模拟客户反馈（非真实用户证据）' in instruction:raise ValueError('model offline')
            return PRODUCT
        run=Run(body(opt=True),'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        self.assertEqual(run.state,'failed')
        delivery=next(e for e in run.events if e['type']=='delivery_checkpoint')
        self.assertIn(PRODUCT,delivery['content'])
        self.assertEqual(delivery['delivery_status'],'provisional')
