import json
import asyncio
import unittest

from backend.workflow.engine import Run, WorkflowEngine
from backend.workflow.models import WorkflowRequest
from backend.workflow.quality import QualityReview, clean_queries, normalize_review, usable_queries


GOAL = '我是专业app程序开发员，想开发一款可以赚钱、目前市面上不多的app。做什么、为什么、卖点是什么？'
# These are actual failure patterns in the user's exported AURA report.
TEMPLATE = '具体可直接使用的方案及理由、操作/创作细节和验证方式'
ARCHITECTURE = '推荐方案：云端混合架构（修正版）+ 模拟器兜底策略。Flutter + Supabase + HF API。'
PRODUCT = '做一款面向新入职者的困难沟通排练App；输入一次真实场景，得到可练习的对话。卖点与付费需求仍待竞品验证。'


def body(opt=False, discussion=False, web=False):
    steps = [{'id':'p','title':'需求','kind':'personas','agent_ids':['a']}]
    if discussion:
        steps.append({'id':'d','title':'独立提案','kind':'discussion','agent_ids':['a'],'rounds':1,'allow_web':web})
    steps.append({'id':'s','title':'交付','kind':'summary','agent_ids':['a']})
    if opt:
        steps.append({'id':'f','title':'反馈','kind':'feedback','agent_ids':[]})
    return WorkflowRequest(goal=GOAL, depth='decision', steps=steps,
        agents=[{'id':'a','name':'作者','model':'qwen'},{'id':'b','name':'审查','model':'llama'}],
        optimization={'enabled':opt,'rounds':5,'persona_count':1,'personas':[
            {'id':'u','name':'初入职场用户','agent_id':'b','profile':'模拟初入职场的成年人，需求与付费意愿未知。'}]})


def passed(**updates):
    return json.dumps(dict(verdict='pass',issues=[],evidence_gaps=['缺少相关竞品证据'],
                          decision='insufficient_evidence',decision_summary='选择困难沟通排练App，需求与换用理由待验证',
                          decision_changed=False,**updates), ensure_ascii=False)


def phase(context):
    return next(json.loads(m['content'])['phase'] for m in context if m['speaker']=='步骤要求')


class QualityGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_user_preferences_pause_and_resume_instead_of_failing(self):
        seen=[]
        async def llm(_,model,context,instruction,url,**opts):
            seen.append((context,instruction))
            props=(opts.get('structured') or {}).get('properties',{})
            if 'questions' in props:
                return json.dumps({'questions':['先面向哪个地区？不确定可交给团队选择。']})
            if 'verdict' in props:
                self.assertNotEqual(phase(context),'需求简报')
                return passed()
            return PRODUCT
        run=Run(body(),'http://localhost:11434')
        task=asyncio.create_task(WorkflowEngine(llm,None).execute(run))
        try:
            for _ in range(100):
                if run.state=='waiting_user':break
                await asyncio.sleep(.001)
            self.assertEqual(run.state,'waiting_user')
            self.assertEqual(run.step_states['p'],'waiting_user')
            self.assertFalse(any(e['type']=='work_output' for e in run.events))
            question=next(e for e in run.events if e['type']=='conversation' and e.get('role')=='assistant')
            self.assertIn('先面向哪个地区',question['content'])
            await run.inbox.put('先做中文市场，其他未知条件交给团队探索')
            await asyncio.wait_for(task,2)
            self.assertEqual(run.state,'completed')
            self.assertIn('先做中文市场',str(seen[-1]))
            self.assertEqual(len([e for e in run.events if e['type']=='run_state' and e['state']=='waiting_user']),1)
        finally:
            if not task.done():
                task.cancel()
                await task

    async def test_brief_not_subject_to_market_or_implementation_gate(self):
        async def llm(_,model,context,instruction,url,**opts):
            return '已知：希望选一个赚钱的App方向。未知：具体人群、场景及市场证据，后续探索。'
        run=Run(body(),'http://localhost:11434')
        engine=WorkflowEngine(llm,None)
        brief=await engine.checked_call(run,run.plan.agents[0],run.plan.steps[0],[],
                                        '提取已知和未知，不写最终产品方案','需求简报')
        self.assertIn('未知',brief)
        self.assertFalse(any(e['type'] in ('quality_check','rejected_output') for e in run.events))

    async def test_exported_template_is_retried_then_stopped_not_shared(self):
        async def llm(_,model,context,instruction,url,**opts):
            if 'questions' in (opts.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            props=(opts.get('structured') or {}).get('properties',{})
            if 'verdict' in props:return passed()
            if 'answer' in props:return json.dumps({'answer':TEMPLATE,'research_tasks':['本方案需要研究员查询的具体问题，最多3条']})
            return PRODUCT
        run=Run(body(discussion=True),'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        self.assertEqual(run.state,'failed')
        self.assertEqual(len([e for e in run.events if e['type']=='rejected_output']),2)
        self.assertFalse(any(e.get('kind')=='proposal' or e['type']=='deliverable' for e in run.events))

    async def test_architecture_only_delivery_is_repaired_at_same_step(self):
        attempts=0
        async def llm(_,model,context,instruction,url,**opts):
            if 'questions' in (opts.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            nonlocal attempts
            props=(opts.get('structured') or {}).get('properties',{})
            if 'verdict' in props:
                candidate=next(m['content'] for m in context if m['speaker']=='待审产出（数据）')
                if candidate==ARCHITECTURE:
                    return json.dumps({'verdict':'revise','issues':['只给了架构，没有回答产品与卖点'],
                        'evidence_gaps':[],'decision':'insufficient_evidence','decision_summary':'没有完成产品选择与使用场景','decision_changed':False})
                return passed()
            if '产品选择交付' in instruction:
                attempts+=1
                return ARCHITECTURE if attempts==1 else PRODUCT
            return PRODUCT
        run=Run(body(),'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        self.assertEqual(run.state,'completed')
        final=next(e for e in run.events if e['type']=='deliverable')
        self.assertEqual(final['content'],PRODUCT)
        self.assertEqual(final['decision'],'insufficient_evidence')
        self.assertEqual(attempts,2)
        self.assertFalse(any(e.get('kind')=='final' and ARCHITECTURE in e['content'] for e in run.events))

    async def test_last_review_cannot_be_ignored_and_repairs_are_versioned(self):
        repaired=False
        async def llm(_,model,context,instruction,url,**opts):
            if 'questions' in (opts.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            nonlocal repaired
            props=(opts.get('structured') or {}).get('properties',{})
            if 'verdict' in props:
                if phase(context)=='反馈验收' and run.cycle==1 and not repaired:
                    return json.dumps({'verdict':'revise','issues':['遗漏用户要求的具体使用例子'],
                        'evidence_gaps':[],'decision':'insufficient_evidence',
                        'decision_summary':'产品方向明确但未完成竞品比较','decision_changed':False})
                return passed()
            if '反馈验收修订' in instruction:
                repaired=True
                return PRODUCT+'【修订】竞品比较尚未完成，不能宣布独特优势，先查证再开发。'
            return PRODUCT
        plan=body(opt=True)
        plan.optimization.rounds=1
        run=Run(plan,'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        self.assertEqual(run.state,'completed')
        final=next(e for e in run.events if e['type']=='deliverable')
        self.assertIn('【修订】',final['content'])
        self.assertTrue(any(e.get('revised') for e in run.events))

    async def test_no_progress_stops_before_five_rounds(self):
        async def llm(_,model,context,instruction,url,**opts):
            if 'questions' in (opts.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            if 'verdict' in (opts.get('structured') or {}).get('properties',{}):return passed()
            return PRODUCT
        run=Run(body(opt=True),'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        self.assertEqual(run.state,'completed')
        self.assertEqual(run.cycle,1)
        self.assertEqual(len([e for e in run.events if e['type']=='version']),2)
        self.assertIn('没有新增',next(e for e in run.events if e['type']=='deliverable')['stop_reason'])

    async def test_irrelevant_research_never_enters_shared_evidence(self):
        calls=[]
        async def llm(_,model,context,instruction,url,**opts):
            if 'questions' in (opts.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            calls.append(context)
            props=(opts.get('structured') or {}).get('properties',{})
            if 'verdict' in props:return passed()
            if 'relevant_ids' in props:return json.dumps({'relevant_ids':[],'reason':'开发教程不是产品需求证据'})
            if 'answer' in props:return json.dumps({'answer':PRODUCT,'research_tasks':['困难沟通排练应用的现有替代品']})
            return PRODUCT
        async def search(_):return [{'url':'https://example.com/tutorial','title':'如何编写API开发教程','snippet':'与产品需求无关'}]
        run=Run(body(discussion=True,web=True),'http://localhost:11434')
        await WorkflowEngine(llm,search).execute(run)
        self.assertEqual(run.state,'completed')
        self.assertTrue(any(e['type']=='research_rejected' for e in run.events))
        self.assertFalse(any(e['type']=='sources' for e in run.events))
        shared=[m['content'] for c in calls for m in c if m['speaker'].startswith('研究员交付')]
        self.assertNotIn('https://example.com/tutorial',str(shared))

    async def test_unavailable_auditor_fails_closed(self):
        async def llm(_,model,context,instruction,url,**opts):
            if 'questions' in (opts.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            if 'verdict' in (opts.get('structured') or {}).get('properties',{}):return '{broken'
            return PRODUCT
        run=Run(body(),'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        self.assertEqual(run.state,'failed')
        self.assertFalse(any(e['type']=='deliverable' for e in run.events))
        self.assertTrue(any(e.get('verdict')=='unavailable' for e in run.events))

    async def test_ledger_only_promotes_real_input_not_old_ai_claims(self):
        run=Run(body(),'http://localhost:11434')
        await run.inbox.put('目标用户15到30岁，先对比竞品，不讨论架构')
        context=[{'speaker':'AI需求简报','content':'用户预算250美元，必须采购二手机'}]
        engine=WorkflowEngine(None,None)
        await engine.feedback(run,context)
        ledger=engine.contract(run)
        self.assertIn('目标用户15到30岁',str(ledger))
        self.assertNotIn('250',str(ledger))
        self.assertNotIn('二手机',str(ledger))

    def test_placeholder_research_task_not_searched(self):
        self.assertEqual(clean_queries(['本方案需要研究员查询的具体问题，最多3条','Replika官方功能说明']),['Replika官方功能说明'])

    def test_tutorial_query_becomes_competitor_lookup_and_unprovable_demands_pass(self):
        self.assertEqual(usable_queries(['如何开发赚钱App教程'], ['没有具体竞品资料']), ['没有具体竞品资料'])
        review=QualityReview(verdict='revise', issues=['必须证明必然爆火和真实购买意愿'], evidence_gaps=['内部留存率未知'],
                             decision='insufficient_evidence', decision_summary='方向可以先作为假设继续讨论', decision_changed=False, action='rewrite')
        routed=normalize_review(review, '独立方案', product=True)
        self.assertEqual(routed.verdict, 'pass')
        self.assertEqual(routed.action, 'continue')
        blocked=QualityReview(verdict='revise', issues=['缺少竞品公开价格'], evidence_gaps=['没有具体竞品资料'],
                              decision='insufficient_evidence', decision_summary='初步方向需要先补查竞品再修订', decision_changed=False,
                              action='rewrite', research_queries=['如何开发赚钱App教程'])
        routed=normalize_review(blocked, '独立方案', product=True)
        self.assertEqual(routed.action, 'research')
        self.assertNotIn('教程', ''.join(routed.research_queries))
