import asyncio
import json
import unittest

from backend.workflow.engine import Run, WorkflowEngine
from backend.workflow.quality import QualityReview
from test_quality_gates import body, passed, PRODUCT, TEMPLATE, phase


def correction(action, **extra):
    data=dict(verdict='revise',issues=['需要补充竞品事实后修订'],evidence_gaps=['缺竞品公开功能'],
              decision='insufficient_evidence',decision_summary='具体产品方向需要竞品对比验证',decision_changed=False,
              action=action,research_queries=['具体竞品官网功能介绍'],user_questions=['先面向哪个市场？'])
    data.update(extra)
    return QualityReview(**data)


class StepReturnTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_evidence_bypasses_without_rewriting_or_asking_user(self):
        generated=[]
        async def llm(_,model,context,instruction,url,**options):
            if 'verdict' in (options.get('structured') or {}).get('properties',{}):
                return correction('research').model_dump_json()
            generated.append(instruction)
            return PRODUCT
        run=Run(body(),'http://localhost:11434')
        text=await WorkflowEngine(llm,None).checked_call(run,run.plan.agents[0],run.plan.steps[-1],[],
                                                       '产品交付','最终交付')
        self.assertEqual(len(generated),1)
        self.assertIn(PRODUCT,text)
        self.assertEqual(run.latest_quality.decision,'insufficient_evidence')
        self.assertTrue(any(e['type']=='evidence_bypass' for e in run.events))
        self.assertFalse(any(e['type']=='step_return' for e in run.events))

    async def test_proposal_can_research_before_acceptance_and_sources_reach_final(self):
        searches=[]
        async def llm(_,model,context,instruction,url,**options):
            props=(options.get('structured') or {}).get('properties',{})
            if 'questions' in props:return json.dumps({'questions':[]})
            if 'verdict' in props:
                evidence=next(m['content'] for m in context if m['speaker'].startswith('最近实际检索来源'))
                if phase(context)=='独立方案' and evidence=='[]':return correction('research').model_dump_json()
                return passed()
            if 'relevant_ids' in props:
                found=json.loads(next(m['content'] for m in context if m['speaker'].startswith('候选搜索摘要')))
                return json.dumps({'relevant_ids':[s['id'] for s in found],'reason':'竞品公开功能相关'})
            if 'answer' in props:return json.dumps({'answer':PRODUCT,'research_tasks':['具体竞品官网功能介绍']})
            return PRODUCT
        async def search(q):
            searches.extend(q)
            return [{'title':'竞品功能','url':'https://example.com/features','snippet':'产品提供场景排练功能'}]
        run=Run(body(discussion=True,web=True),'http://localhost:11434')
        await WorkflowEngine(llm,search).execute(run)
        self.assertEqual(run.state,'completed')
        route=next(e for e in run.events if e['type']=='step_return' and e['state']=='running')
        self.assertEqual(route['action'],'research')
        first_accepted=next(e for e in run.events if e.get('kind')=='proposal')
        self.assertLess(route['seq'],first_accepted['seq'])
        self.assertTrue(searches)
        self.assertTrue(next(e for e in run.events if e['type']=='deliverable')['sources'])
        self.assertEqual(len([e for e in run.events if e['type']=='task_contract']),1)

    async def test_return_clarification_waits_then_updates_contract_without_regenerating_personas(self):
        run=Run(body(),'http://localhost:11434')
        context=[]
        engine=WorkflowEngine(None,None)
        task=asyncio.create_task(engine.return_to_step(run,run.plan.agents[0],run.plan.steps[-1],context,correction('clarify'),PRODUCT))
        try:
            for _ in range(100):
                if run.state=='waiting_user':break
                await asyncio.sleep(.001)
            self.assertEqual(run.state,'waiting_user')
            self.assertEqual(run.step_states['p'],'waiting_user')
            await run.inbox.put('先做中文市场，其余交给团队探索')
            await asyncio.wait_for(task,2)
            self.assertEqual(run.state,'running')
            self.assertIn('先做中文市场',str(engine.contract(run)))
            self.assertEqual(run.step_states['s'],'running')
            self.assertFalse(any(e['type']=='personas_updated' for e in run.events))
        finally:
            if not task.done():task.cancel();await task

    async def test_no_web_permission_yields_explicit_gap_not_unauthorized_search(self):
        async def search(_):self.fail('Should not search without permission')
        run=Run(body(),'http://localhost:11434')
        context=[]
        await WorkflowEngine(None,search).return_to_step(run,run.plan.agents[0],run.plan.steps[-1],context,correction('research'),PRODUCT)
        self.assertTrue(any(e['type']=='step_return' and e['state']=='blocked' for e in run.events))
        self.assertIn('没有授权联网',str(context))

    async def test_discussion_return_preserves_independent_contexts_and_has_limit(self):
        contexts=[]
        async def llm(_,model,context,instruction,url,**options):
            contexts.append(list(context))
            return PRODUCT+model
        plan=body(discussion=True)
        plan.steps[1].agent_ids=['a','b']
        run=Run(plan,'http://localhost:11434')
        engine=WorkflowEngine(llm,None)
        context=[]
        for _ in range(3):
            await engine.return_to_step(run,plan.agents[0],plan.steps[-1],context,correction('discuss'),PRODUCT)
        self.assertEqual(len(contexts),4)
        self.assertEqual(contexts[0],contexts[1])
        self.assertEqual(run.returns['s'],2)
        self.assertTrue(any(e['type']=='warning' and '上限' in e.get('content','') for e in run.events))

    async def test_unavailable_evidence_is_qualified_outcome_not_dead_end(self):
        async def llm(_,model,context,instruction,url,**options):
            props=(options.get('structured') or {}).get('properties',{})
            if 'verdict' in props:return correction('research').model_dump_json()
            return PRODUCT
        run=Run(body(),'http://localhost:11434')
        engine=WorkflowEngine(llm,None)
        text=await engine.checked_call(run,run.plan.agents[0],run.plan.steps[-1],[],'交付产品选择','最终交付')
        self.assertIn('证据不足',text)
        self.assertEqual(run.latest_quality.decision,'insufficient_evidence')
        self.assertNotIn('两次检查未通过',text)

    async def test_mislabeled_evidence_block_returns_to_competitor_research(self):
        searches=[]
        async def llm(_,model,context,instruction,url,**options):
            props=(options.get('structured') or {}).get('properties',{})
            if 'questions' in props:return json.dumps({'questions':[]})
            if 'verdict' in props:
                evidence=next(m['content'] for m in context if m['speaker'].startswith('最近实际检索来源'))
                if phase(context)=='独立方案' and 'example.com/competitor' not in evidence:
                    return json.dumps({'verdict':'revise','issues':['缺少竞品公开功能、价格和用户评价，不能通过'],
                        'evidence_gaps':['没有具体竞品资料'],'decision':'insufficient_evidence',
                        'decision_summary':'初步方向需要先补查竞品再修订','decision_changed':False,
                        'action':'rewrite','research_queries':['如何开发赚钱App教程'],'user_questions':[]})
                return passed()
            if 'relevant_ids' in props:
                found=json.loads(next(m['content'] for m in context if m['speaker'].startswith('候选搜索摘要')))
                return json.dumps({'relevant_ids':[s['id'] for s in found if '教程' not in s.get('title','')],'reason':'只要竞品公开信息'})
            if 'answer' in props:return json.dumps({'answer':PRODUCT,'research_tasks':['Replika 公开功能与价格']})
            return PRODUCT
        async def search(q):
            searches.extend(q)
            if any('教程' in item or '如何开发' in item for item in q):
                return [{'title':'如何开发赚钱App教程','url':'https://example.com/tutorial','snippet':'手把手开发教程'}]
            return [{'title':'Replika功能与价格','url':'https://example.com/competitor','snippet':'公开功能与订阅价格'}]
        run=Run(body(discussion=True,web=True),'http://localhost:11434')
        await WorkflowEngine(llm,search).execute(run)
        self.assertEqual(run.state,'completed', [e for e in run.events if e['type'] in ('error','warning')][-3:])
        self.assertTrue(any(e['type']=='step_return' and e['action']=='research' for e in run.events))
        self.assertTrue(any(e['type']=='sources' and any('competitor' in s.get('url','') for s in e['sources']) for e in run.events))
        self.assertFalse(any('如何开发' in q or '教程' in q for q in searches))
        self.assertTrue(any(e.get('kind')=='proposal' for e in run.events))
        self.assertFalse(any(e['type']=='personas_updated' for e in run.events))
        self.assertFalse(any(e['type']=='error' for e in run.events))

    async def test_unprovable_demands_do_not_block_a_preliminary_proposal(self):
        async def llm(_,model,context,instruction,url,**options):
            props=(options.get('structured') or {}).get('properties',{})
            if 'questions' in props:return json.dumps({'questions':[]})
            if 'verdict' in props:
                if phase(context)=='独立方案':
                    return json.dumps({'verdict':'revise','issues':['必须证明必然爆火、竞品内部留存率和真实购买意愿后才能继续'],
                        'evidence_gaps':['内部留存率未知'],'decision':'insufficient_evidence',
                        'decision_summary':'方向可以先作为有标注的假设继续','decision_changed':False,'action':'rewrite'})
                return passed()
            if 'answer' in props:return json.dumps({'answer':PRODUCT,'research_tasks':[]})
            return PRODUCT
        run=Run(body(discussion=True),'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        self.assertEqual(run.state,'completed')
        self.assertTrue(any(e.get('kind')=='proposal' for e in run.events))
        self.assertFalse(any(e['type']=='step_return' for e in run.events))
        self.assertFalse(any(e['type']=='personas_updated' for e in run.events))

    async def test_one_missing_member_does_not_block_other_research(self):
        searches=[]
        async def llm(_,model,context,instruction,url,**options):
            props=(options.get('structured') or {}).get('properties',{})
            if 'questions' in props:return json.dumps({'questions':[]})
            if 'verdict' in props:return passed()
            if 'relevant_ids' in props:
                found=json.loads(next(m['content'] for m in context if m['speaker'].startswith('候选搜索摘要')))
                return json.dumps({'relevant_ids':[s['id'] for s in found],'reason':'竞品公开功能相关'})
            if 'answer' in props:
                if model=='llama':return json.dumps({'answer':TEMPLATE,'research_tasks':[]})
                return json.dumps({'answer':PRODUCT,'research_tasks':['Replika 公开功能与价格']})
            return PRODUCT
        async def search(q):
            searches.extend(q)
            return [{'title':'Replika功能与价格','url':'https://example.com/competitor','snippet':'公开功能与订阅价格'}]
        plan=body(discussion=True,web=True)
        plan.steps[1].agent_ids=['a','b']
        run=Run(plan,'http://localhost:11434')
        await WorkflowEngine(llm,search).execute(run)
        self.assertEqual(run.state,'completed')
        self.assertTrue(searches)
        self.assertTrue(any(e['type']=='warning' and '不是全体共识' in e.get('content','') for e in run.events))
        self.assertFalse(any(e['type']=='error' for e in run.events))
