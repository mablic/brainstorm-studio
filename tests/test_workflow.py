import asyncio
import json
import unittest

from pydantic import ValidationError
from backend.workflow.models import WorkflowRequest, ConnectionRequest
from backend.workflow.engine import Run, WorkflowEngine


def plan(web=True):
    return WorkflowRequest(goal='Create a practical video', agents=[
        {'id': key, 'name': key, 'model': key} for key in ['a', 'b']], steps=[
        {'id': 'clarify', 'title': 'Clarify', 'kind': 'clarify', 'agent_ids': ['a']},
        {'id': 'discuss', 'title': 'Discuss', 'kind': 'discussion',
         'agent_ids': ['a', 'b'], 'rounds': 2, 'allow_web': web},
        {'id': 'finish', 'title': 'Deliver', 'kind': 'summary', 'agent_ids': ['a']},
    ])


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_discussion_delegates_to_shared_researcher_and_shares_next_round(self):
        calls=[]
        async def llm(_,model,context,instruction,url,**options):
            calls.append((model,list(context),instruction))
            if options.get('structured'):
                return json.dumps({'answer':model+' independent concrete product proposal','research_tasks':[model+' competitor features']})
            if '制定搜索查询' in instruction:return json.dumps(['initial evidence'])
            return 'Research findings with evidence and known limitations'
        async def search(queries):
            return [{'title':queries[0],'url':'https://example.com/'+queries[0].replace(' ','-'),'snippet':'actual search result'}]
        data=plan(False).model_dump()
        data['revision']={'previous_result':'Old draft','feedback':'Compare competitors'}
        data['steps'].insert(1,{'id':'research','kind':'research','title':'Shared researcher','agent_ids':['b'],'allow_web':True})
        run=Run(WorkflowRequest(**data),'http://localhost:11434')
        await WorkflowEngine(llm,search).execute(run)
        self.assertEqual(run.state,'completed')
        dispatch=[e for e in run.events if e['type']=='research_dispatch']
        self.assertEqual(len(dispatch),4)
        self.assertTrue(all(e['researcher']=='b' for e in dispatch))
        discussions=[c for c in calls if 'research_tasks' in c[2]]
        self.assertEqual(discussions[0][1],discussions[1][1])
        self.assertEqual(discussions[2][1],discussions[3][1])
        self.assertIn('a competitor features',str(discussions[2][1]))
        self.assertIn('b competitor features',str(discussions[2][1]))

    async def test_independence_research_and_user_gate(self):
        calls, searches = [], []

        async def llm(client, model, context, instruction, base_url, **options):
            calls.append((model, list(context), instruction))
            if options.get('structured'):
                return json.dumps({'answer': f'{model} concrete independent proposal',
                                   'research_tasks': [f'verify {model}']})
            return 'Practical questions, brief or deliverable'

        async def search(queries):
            searches.extend(queries)
            return [{'title': 'Evidence', 'url': 'https://example.com', 'snippet': 'source'}]

        run = Run(plan(), 'http://localhost:11434')
        task = asyncio.create_task(WorkflowEngine(llm, search).execute(run))
        for _ in range(100):
            if run.state == 'waiting_user':
                break
            await asyncio.sleep(.001)
        self.assertEqual(run.state, 'waiting_user')
        self.assertEqual(len(calls), 1)
        self.assertFalse(searches)
        await run.inbox.put('Audience: young women, budget 100')
        await asyncio.wait_for(task, 2)
        self.assertEqual(run.state, 'completed')
        discussions = [c for c in calls if 'research_tasks' in c[2]]
        self.assertEqual(len(discussions), 4)
        self.assertEqual(discussions[0][1], discussions[1][1])
        self.assertEqual(discussions[2][1], discussions[3][1])
        self.assertFalse(any('proposal' in x['content'] for x in discussions[0][1]))
        self.assertTrue(any('proposal' in x['content'] for x in discussions[2][1]))
        self.assertTrue(any('Evidence' in x['content'] for x in discussions[2][1]))
        self.assertEqual(searches, ['verify a', 'verify b', 'verify a', 'verify b'])
        self.assertTrue(any(e['type'] == 'deliverable' for e in run.events))

    async def test_no_web_without_permission(self):
        async def llm(*args, **kwargs):
            return json.dumps({'answer': 'A concrete usable proposal', 'research_tasks': ['ignored query']}) if kwargs.get('structured') else 'Useful output'
        async def search(_):
            self.fail('Unauthorized search')
        run = Run(plan(False), 'http://localhost:11434')
        task = asyncio.create_task(WorkflowEngine(llm, search).execute(run))
        for _ in range(100):
            if run.state == 'waiting_user':
                break
            await asyncio.sleep(.001)
        await run.inbox.put('User constraints')
        await asyncio.wait_for(task, 2)
        self.assertEqual(run.state, 'completed')

    async def test_cancel_while_waiting(self):
        async def llm(*args, **kwargs):
            return 'Questions'
        run = Run(plan(), 'http://localhost:11434')
        task = asyncio.create_task(WorkflowEngine(llm, None).execute(run))
        for _ in range(100):
            if run.state == 'waiting_user':
                break
            await asyncio.sleep(.001)
        task.cancel()
        await task
        self.assertEqual(run.state, 'cancelled')
        self.assertEqual(run.step_states['clarify'], 'cancelled')

    async def test_failure_marks_step(self):
        async def llm(*args, **kwargs):
            raise ValueError('Model unavailable')
        run = Run(plan(), 'http://localhost:11434')
        await WorkflowEngine(llm, None).execute(run)
        self.assertEqual(run.state, 'failed')
        self.assertEqual(run.step_states['clarify'], 'failed')

    async def test_revision_runs_all_steps_with_previous_result_and_feedback(self):
        calls = []
        async def llm(client, model, context, instruction, base_url, **kwargs):
            calls.append((list(context), instruction))
            if kwargs.get('structured'):
                return json.dumps({'answer': 'Updated practical lower cost proposal', 'research_tasks': []})
            return 'Updated requirements and revised deliverable'
        async def search(_):
            self.fail('Revision must respect disabled web permission')
        body = plan(False).model_dump()
        body['revision'] = {'previous_result': 'Old expensive recommendation',
                            'feedback': 'Reduce budget to 100',
                            'requirements': 'Audience and constraints already confirmed',
                            'evidence': '[Rold-W2] Previous source'}
        run = Run(WorkflowRequest(**body), 'http://localhost:11434')
        await asyncio.wait_for(WorkflowEngine(llm, search).execute(run), 2)
        self.assertEqual(run.state, 'completed')
        self.assertEqual(set(run.step_states.values()), {'completed'})
        self.assertEqual(len(calls), 6)
        for context, instruction in calls:
            contents = '\n'.join(m['content'] for m in context)
            self.assertIn('Old expensive recommendation', contents)
            self.assertIn('Reduce budget to 100', contents)
            self.assertIn('Audience and constraints already confirmed', contents)
            self.assertNotIn('WORKFLOW_CLARIFY', instruction)
        self.assertFalse(any(e.get('state') == 'waiting_user' for e in run.events))
        self.assertTrue(any(e['type'] == 'conversation' and 'Reduce budget' in e['content'] for e in run.events))

    def test_blank_revision_feedback_is_rejected(self):
        body = plan().model_dump()
        body['revision'] = {'previous_result': 'Old result', 'feedback': '  '}
        with self.assertRaises(ValidationError):
            WorkflowRequest(**body)

    async def test_persona_loop_independent_reviews_and_real_user_priority(self):
        calls = []
        async def llm(client, model, context, instruction, base_url, **kwargs):
            calls.append((list(context), instruction))
            if '模拟客户反馈（非真实用户证据）' in instruction:
                return 'Specific blocker: remove costly equipment. Acceptance: budget under 100.'
            if kwargs.get('structured'):
                return json.dumps({'answer': 'Concrete updated proposal with existing resources', 'research_tasks': []})
            return 'Confirmed brief or practical executable recommendation'
        body = plan(False).model_dump()
        body['revision'] = {'previous_result': 'Previous draft', 'feedback': 'Real user budget under 100'}
        body['optimization'] = {'enabled': True, 'rounds': 2, 'personas': [
            {'id': 'p1', 'name': 'Novice', 'agent_id': 'a', 'profile': 'Fixed novice background and constraints'},
            {'id': 'p2', 'name': 'Skeptic', 'agent_id': 'b', 'profile': 'Fixed cautious background and constraints'}]}
        run = Run(WorkflowRequest(**body), 'http://localhost:11434')
        await asyncio.wait_for(WorkflowEngine(llm, None).execute(run), 2)
        self.assertEqual(run.state, 'completed')
        versions = [e for e in run.events if e['type'] == 'version']
        self.assertEqual([e['cycle'] for e in versions], [0, 1, 2])
        reviews = [e for e in run.events if e['type'] == 'persona_feedback']
        self.assertEqual(len(reviews), 6)
        review_calls = [(c,i) for c,i in calls if '模拟客户反馈（非真实用户证据）' in i]
        self.assertEqual(review_calls[0][0], review_calls[1][0])
        self.assertFalse(any('Specific blocker:' in m['content'] for m in review_calls[0][0]))
        next_round = next(c for c,i in calls if 'Specific blocker:' in str(c) and '需求确认简报' in i)
        self.assertIn('Real user budget under 100', str(next_round))
        self.assertTrue(all(r['simulated'] for r in reviews))

    async def test_failed_persona_does_not_fake_success_or_drop_version(self):
        async def llm(client, model, context, instruction, base_url, **kwargs):
            if '模拟客户反馈（非真实用户证据）' in instruction:
                raise ValueError('Reviewer unavailable')
            return 'Preserved detailed draft'
        body = plan(False).model_dump()
        body['steps'] = [body['steps'][0], body['steps'][-1]]
        body['revision'] = {'previous_result': 'Earlier', 'feedback': 'Improve it'}
        body['optimization'] = {'enabled': True, 'rounds': 1, 'personas': [
            {'id':'p', 'name':'Reader', 'agent_id':'b', 'profile':'Known fixed background only'}]}
        run = Run(WorkflowRequest(**body), 'http://localhost:11434')
        await WorkflowEngine(llm, None).execute(run)
        self.assertEqual(run.state, 'failed')
        self.assertEqual(len([e for e in run.events if e['type']=='version']),1)
        retained=[e for e in run.events if e['type']=='deliverable']
        self.assertTrue(all(e.get('incomplete') for e in retained))
        self.assertFalse(any(e['type']=='run_state' and e['state']=='completed' for e in run.events))

    async def test_deep_decision_generates_comparison_then_execution(self):
        calls=[]
        async def llm(client, model, context, instruction, base_url, **kwargs):
            if 'verdict' in (kwargs.get('structured') or {}).get('properties', {}):
                return json.dumps({'verdict':'pass','issues':[],'evidence_gaps':[],
                                   'decision':'suggest_validation','decision_summary':'Concrete video recommendation and reasons','decision_changed':True})
            calls.append(instruction)
            return 'Decision comparison with resources and actions'
        body=plan(False).model_dump()
        body['steps']=[body['steps'][0],body['steps'][-1]]
        body['revision']={'previous_result':'Prior plan','feedback':'Add detail'}
        body['depth']='decision'
        run=Run(WorkflowRequest(**body),'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        self.assertEqual(run.state,'completed')
        self.assertEqual(len(calls),3)
        self.assertIn('决策评估底稿', calls[1])
        self.assertIn('具体执行交付', calls[2])

    def test_optimization_requires_known_reviewers_and_final_delivery(self):
        body=plan().model_dump()
        body['optimization']={'enabled':True,'rounds':1,'personas':[]}
        with self.assertRaises(ValidationError): WorkflowRequest(**body)
        body['optimization']['personas']=[{'id':'p','name':'Reader','agent_id':'unknown','profile':'Fixed known background'}]
        with self.assertRaises(ValidationError): WorkflowRequest(**body)
        body['optimization']['personas'][0]['agent_id']='a'
        body['steps']=body['steps'][:-1]
        with self.assertRaises(ValidationError): WorkflowRequest(**body)

    async def test_real_feedback_during_final_review_is_not_silently_dropped(self):
        run = None
        async def llm(client, model, context, instruction, base_url, **kwargs):
            if '模拟客户反馈（非真实用户证据）' in instruction and run.cycle == 1:
                await run.inbox.put('New real requirement during review')
            return 'Concrete final output with resources and checks'
        body = plan(False).model_dump()
        body['steps'] = [body['steps'][0], body['steps'][-1]]
        body['revision'] = {'previous_result':'Prior', 'feedback':'Improve'}
        body['optimization'] = {'enabled':True, 'rounds':1, 'personas':[
            {'id':'p', 'name':'Reader', 'agent_id':'b', 'profile':'Fixed background and constraints'}]}
        run = Run(WorkflowRequest(**body), 'http://localhost:11434')
        await WorkflowEngine(llm,None).execute(run)
        self.assertEqual(run.state,'completed')
        self.assertTrue(any(e['type']=='work_output' and '纳入最新用户补充' in e.get('title','') for e in run.events))

    async def test_original_clarification_survives_short_briefs_across_cycles(self):
        seen=[]
        async def llm(client, model, context, instruction, base_url, **kwargs):
            seen.append(list(context))
            return 'Short brief intentionally omits the price'
        body=plan(False).model_dump()
        body['steps']=[body['steps'][0],body['steps'][-1]]
        body['optimization']={'enabled':True,'rounds':1,'personas':[
            {'id':'p','name':'Reader','agent_id':'b','profile':'Fixed local constraints and background'}]}
        run=Run(WorkflowRequest(**body),'http://localhost:11434')
        task=asyncio.create_task(WorkflowEngine(llm,None).execute(run))
        for _ in range(100):
            if run.state=='waiting_user':break
            await asyncio.sleep(.001)
        await run.inbox.put('Price 20, material cost 8, do not buy equipment')
        await asyncio.wait_for(task,2)
        self.assertEqual(run.state,'completed')
        self.assertIn('Price 20, material cost 8',str(seen[-1]))

    async def test_cancel_during_persona_review_preserves_draft(self):
        reviewing=asyncio.Event()
        async def llm(client, model, context, instruction, base_url, **kwargs):
            if '模拟客户反馈（非真实用户证据）' in instruction:
                reviewing.set()
                await asyncio.Event().wait()
            return 'Detailed draft retained before review'
        body=plan(False).model_dump()
        body['steps']=[body['steps'][0],body['steps'][-1]]
        body['revision']={'previous_result':'Previous','feedback':'Improve'}
        body['optimization']={'enabled':True,'rounds':1,'personas':[
            {'id':'p','name':'Reader','agent_id':'b','profile':'Fixed background and known constraints'}]}
        run=Run(WorkflowRequest(**body),'http://localhost:11434')
        task=asyncio.create_task(WorkflowEngine(llm,None).execute(run))
        await asyncio.wait_for(reviewing.wait(),2)
        task.cancel()
        await task
        self.assertEqual(run.state,'cancelled')
        self.assertEqual(run.step_states['persona-p'],'cancelled')
        self.assertTrue(any(e['type']=='version' for e in run.events))

    def test_local_only_and_fixed_first_step(self):
        for url in ['https://api.openai.com', 'http://8.8.8.8', 'http://localhost/api/chat']:
            with self.assertRaises(ValidationError):
                ConnectionRequest(base_url=url)
        self.assertEqual(ConnectionRequest(base_url='http://192.168.1.10:11434/').base_url,
                         'http://192.168.1.10:11434')
        data = plan().model_dump()
        data['steps'][0]['agent_ids'] = ['a', 'b']
        with self.assertRaises(ValidationError):
            WorkflowRequest(**data)


if __name__ == '__main__':
    unittest.main()
