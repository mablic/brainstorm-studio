import asyncio
import json
import unittest
from backend.workflow.models import WorkflowRequest, PersonaRequest, Persona
from backend.workflow.engine import Run, WorkflowEngine


def plan():
    return WorkflowRequest(goal='Professional app developer: app for ages 15-30',
        agents=[{'id':'a','name':'Advisor','model':'qwen3.5:9b'}],
        steps=[{'id':'c','title':'Clarify','kind':'clarify','agent_ids':['a']},
               {'id':'s','title':'Deliver','kind':'summary','agent_ids':['a']}],
        optimization={'enabled':True,'rounds':1,'auto_generate':True,'persona_count':2})


class PersonaTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_flow_generates_personas_first_then_reviews_once_each_cycle(self):
        calls=[]
        async def llm(client,model,context,instruction,url,**options):
            if 'questions' in (options.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            calls.append(instruction)
            schema=options.get('structured') or {}
            if 'personas' in schema.get('properties',{}):
                count=schema['properties']['personas']['minItems']
                return json.dumps({'personas':[{'name':f'Segment {i}','profile':'Hypothetical age group and known constraints only'} for i in range(count)]})
            return 'Concrete output with constraints and checks'
        body=plan().model_dump()
        body['steps'][0]['kind']='personas'
        body['steps'].append({'id':'f','title':'User feedback','kind':'feedback','agent_ids':[],'instructions':'Find concrete blockers'})
        run=Run(WorkflowRequest(**body),'http://localhost:11434')
        await asyncio.wait_for(WorkflowEngine(llm,None).execute(run),2)
        self.assertEqual(run.state,'completed')
        self.assertFalse(any(e.get('state')=='waiting_user' for e in run.events))
        self.assertEqual(len([e for e in run.events if e['type']=='personas_updated']),1)
        self.assertEqual(len([e for e in run.events if e['type']=='persona_feedback']),4)
        self.assertEqual(len([e for e in run.events if e['type']=='version']),2)
        self.assertEqual(run.step_states['f'],'completed')
        self.assertTrue('自动识别需求' in calls[0])
        self.assertTrue(any('Find concrete blockers' in i for i in calls))

    async def test_generation_after_answer_and_queued_addition_before_review(self):
        generations=[]
        async def llm(client,model,context,instruction,url,**options):
            if 'questions' in (options.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            schema=options.get('structured') or {}
            if 'personas' in schema.get('properties',{}):
                generations.append((context,instruction))
                count=schema['properties']['personas']['minItems']
                return json.dumps({'personas':[{'name':f'Segment {len(generations)}-{i}',
                    'profile':'Known age range; hypothetical student context; income and payment willingness unknown.'} for i in range(count)]})
            return 'A brief, final output or independent simulated review'
        run=Run(plan(),'http://localhost:11434')
        task=asyncio.create_task(WorkflowEngine(llm,None).execute(run))
        for _ in range(100):
            if run.state=='waiting_user':break
            await asyncio.sleep(.001)
        self.assertEqual(generations,[])
        run.persona_requests.append(PersonaRequest(hint='Add a privacy-sensitive adult'))
        await run.inbox.put('Students and young professionals; limited budget; no proven demand yet')
        await asyncio.wait_for(task,2)
        self.assertEqual(run.state,'completed')
        self.assertEqual(len(generations),2)
        self.assertIn('Students and young professionals',str(generations[0][0]))
        self.assertIn('privacy-sensitive adult',str(generations[1][0]))
        self.assertEqual(len(run.plan.optimization.personas),3)
        self.assertEqual(len([e for e in run.events if e['type']=='persona_feedback']),6)
        self.assertTrue(run.personas_locked)
        first_update=next(e['seq'] for e in run.events if e['type']=='personas_updated')
        first_review=next(e['seq'] for e in run.events if e['type']=='persona_feedback')
        self.assertLess(first_update,first_review)

    async def test_manual_changes_win_over_inflight_generation(self):
        run=Run(plan(),'http://localhost:11434')
        manual=Persona(id='manual',name='My segment',profile='My fixed custom profile and known constraints',agent_id='a')
        async def llm(*args,**kwargs):
            if 'questions' in (kwargs.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            run.plan.optimization.personas=[manual]
            run.personas_revision+=1
            return json.dumps({'personas':[{'name':'Generated','profile':'Generated profile with hypothetical background'}]})
        await WorkflowEngine(llm,None).generate_personas(run,{'a':run.plan.agents[0]},[],1)
        self.assertEqual(run.plan.optimization.personas,[manual])
        self.assertTrue(any(e['type']=='warning' for e in run.events))

    async def test_malformed_generation_does_not_create_fake_profiles(self):
        async def llm(*args,**kwargs):return 'Malformed incomplete output'
        run=Run(plan(),'http://localhost:11434')
        with self.assertRaises(ValueError):
            await WorkflowEngine(llm,None).generate_personas(run,{'a':run.plan.agents[0]},[],2)
        self.assertEqual(run.plan.optimization.personas,[])
        self.assertEqual(run.step_states['persona-generation'],'failed')
