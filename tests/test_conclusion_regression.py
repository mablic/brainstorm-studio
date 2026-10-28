"""Regressions from brainstorm-workspace.md: truncated Glimmer and erased recommendations."""
import json
import unittest
import httpx
from backend.main import answer
from backend.workflow.engine import Run, WorkflowEngine
from backend.workflow.quality import QualityReview, incomplete_output, usable_queries
from test_quality_gates import body, PRODUCT

def evidence_review():
    return QualityReview(verdict='revise',issues=['没有具体竞品的公开功能对比'],
        evidence_gaps=['竞品资料未查证'], decision='insufficient_evidence',
        decision_summary='暂选困难沟通排练工具，先验证替代品差异，再决定是否开发。',
        decision_changed=False,action='research',research_queries=['沟通排练 应用 公开功能'])

class TruncationTests(unittest.IsolatedAsyncioTestCase):
    async def test_third_attempt_requests_short_complete_result(self):
        calls=[]
        def handle(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'message':{'content':PRODUCT},'done_reason':'length' if len(calls)<3 else 'stop'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            text=await answer(client,'qwen3.5:9b',[],'产品结论',max_tokens=1200)
        self.assertEqual(text,PRODUCT)
        self.assertEqual(len(calls),3)
        self.assertIn('精简恢复',calls[-1]['messages'][0]['content'])
        self.assertEqual(calls[-1]['options']['num_predict'],2000)

    async def test_query_generation_length_failure_does_not_abort_workflow(self):
        async def llm(*args,**kwargs):raise ValueError('模型连续达到输出上限，正文不完整')
        run=Run(body(),'http://localhost:11434')
        result=await WorkflowEngine(llm,None).query_plan(run,run.plan.agents[0],run.plan.steps[-1],[], '生成搜索查询')
        self.assertEqual(result,[])
        self.assertTrue(any('跳过辅助检索' in e.get('content','') for e in run.events))

    async def test_nonempty_length_response_is_retried_not_delivered(self):
        calls=[]
        def handle(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'message':{'content':'开发一款名为“微光' if len(calls)==1 else PRODUCT},
                                          'done_reason':'length' if len(calls)==1 else 'stop'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result=await answer(client,'qwen3.5:9b',[],'完整建议',max_tokens=1200)
        self.assertEqual(result,PRODUCT)
        self.assertEqual([p['options']['num_predict'] for p in calls],[1200,2400])

    async def test_repeated_truncation_stops_instead_of_reviewing_fragment(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'message':{'content':PRODUCT},'done_reason':'length'}))) as client:
            with self.assertRaisesRegex(ValueError,'正文不完整'):
                await answer(client,'qwen3.5:9b',[],'完整建议')

    def test_actual_export_fragment_rejected_but_short_complete_answer_allowed(self):
        self.assertIsNotNone(incomplete_output('开发一款名为 **“微光 (Glimmer)'))
        self.assertIsNotNone(incomplete_output('## 推荐方案'))
        self.assertIsNone(incomplete_output(PRODUCT))

class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def test_bounded_evidence_fallback_keeps_concrete_choice(self):
        run=Run(body(),'http://localhost:11434')
        engine=WorkflowEngine(None,None)
        result=engine.qualified_outcome(run,'最终交付',PRODUCT,evidence_review())
        self.assertIn(PRODUCT,result)
        self.assertIn('证据',result)
        again=engine.qualified_outcome(run,'最终交付',result,evidence_review())
        self.assertEqual(again.count(PRODUCT),1)
        self.assertEqual(again.count('### 候选方案（待验证）'),1)

    async def test_last_evidence_review_delivers_provisional_conclusion_not_error(self):
        async def llm(_,model,context,instruction,url,**options):
            props=(options.get('structured') or {}).get('properties',{})
            if 'questions' in props: return json.dumps({'questions':[]})
            if 'verdict' in props: return evidence_review().model_dump_json()
            return PRODUCT
        run=Run(body(opt=True),'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        self.assertEqual(run.state,'completed', [e for e in run.events if e['type']=='error'])
        final=next(e for e in run.events if e['type']=='deliverable')
        self.assertEqual(final['delivery_status'],'provisional')
        self.assertEqual(final['decision'],'insufficient_evidence')
        self.assertIn(PRODUCT,final['content'])
        self.assertTrue(final['evidence_gaps'])
        self.assertTrue(final['stop_reason'])
        self.assertFalse(any(e['type']=='error' for e in run.events))

    def test_research_queries_are_not_review_complaints_or_private_experiments(self):
        queries=usable_queries(['未提供开发资源、时间和技术栈细节','未进行用户付费意愿测试','沟通排练 App 官方功能'])
        self.assertEqual(queries,['沟通排练 App 官方功能'])
