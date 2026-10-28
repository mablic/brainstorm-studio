import time
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.workflow.router import create_workflow_router


class WorkflowApiTests(unittest.TestCase):
    def test_persona_first_flow_completes_without_extra_user_confirmation(self):
        import json
        async def answer(client,model,context,instruction,url,**options):
            if 'questions' in (options.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            schema=options.get('structured') or {}
            if 'personas' in schema.get('properties',{}):
                count=schema['properties']['personas']['minItems']
                return json.dumps({'personas':[{'name':f'Segment {i}','profile':'Hypothetical needs and context, not verified demand'} for i in range(count)]})
            return 'Concrete deliverable or independent feedback with checks'
        async def resolve(client):return 'http://localhost:11434'
        async def installed(client,url):return [{'name':'test'}]
        app=FastAPI();app.include_router(create_workflow_router(answer,resolve,installed))
        body={'goal':'App for ages 15-30','agents':[{'id':'a','name':'Advisor','model':'test'}],
              'steps':[{'id':'p','title':'Generate personas','kind':'personas','agent_ids':['a']},
                       {'id':'s','title':'Deliver','kind':'summary','agent_ids':['a']},
                       {'id':'f','title':'Simulated feedback','kind':'feedback','agent_ids':[]}],
              'optimization':{'enabled':True,'rounds':1,'auto_generate':True,'persona_count':2}}
        with TestClient(app) as client:
            response=client.post('/api/workflow/runs',json=body)
            self.assertEqual(response.status_code,200)
            url='/api/workflow/runs/'+response.json()['id']
            for _ in range(200):
                if client.get(url).json()['state']=='completed':break
                time.sleep(.005)
            self.assertEqual(client.get(url).json()['state'],'completed')
            events=[json.loads(line) for line in client.get(url+'/events').text.splitlines()]
            self.assertFalse(any(e.get('state')=='waiting_user' for e in events))
            self.assertEqual(len([e for e in events if e['type']=='version']),2)
            self.assertTrue(any(e['type']=='step_state' and e['step_id']=='f' and e['state']=='running' for e in events))

    def test_live_personas_update_queue_and_review_lock(self):
        import asyncio,json,threading
        release=threading.Event()
        async def answer(client,model,context,instruction,url,**options):
            if 'questions' in (options.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            schema=options.get('structured') or {}
            if 'personas' in schema.get('properties',{}):
                count=schema['properties']['personas']['minItems']
                return json.dumps({'personas':[{'name':f'Generated {i}','profile':'Hypothetical background with known user constraints'} for i in range(count)]})
            if '模拟客户反馈（非真实用户证据）' in instruction:
                while not release.is_set():await asyncio.sleep(.005)
            return 'Detailed final output or brief'
        async def resolve(client):return 'http://localhost:11434'
        async def installed(client,url):return [{'name':'test'}]
        app=FastAPI();app.include_router(create_workflow_router(answer,resolve,installed))
        body={'goal':'App for young users','agents':[{'id':'a','name':'Advisor','model':'test'}],
              'steps':[{'id':'c','title':'Clarify','kind':'clarify','agent_ids':['a']},
                       {'id':'s','title':'Deliver','kind':'summary','agent_ids':['a']}],
              'optimization':{'enabled':True,'rounds':1,'auto_generate':True,'persona_count':2}}
        with TestClient(app) as client:
            response=client.post('/api/workflow/runs',json=body)
            self.assertEqual(response.status_code,200)
            url='/api/workflow/runs/'+response.json()['id']
            for _ in range(100):
                if client.get(url).json()['state']=='waiting_user':break
                time.sleep(.005)
            manual={'id':'p','name':'Specific reader','profile':'Known fixed background and constraints','agent_id':'a'}
            self.assertEqual(client.put(url+'/personas',json={'personas':[manual]}).status_code,200)
            self.assertEqual(client.post(url+'/personas/generate',json={'hint':'Privacy-aware user'}).status_code,200)
            self.assertEqual(client.get(url).json()['personas'][0]['name'],'Specific reader')
            client.post(url+'/messages',json={'text':'Confirmed audience and constraints'})
            for _ in range(200):
                if client.get(url).json()['personas_locked']:break
                time.sleep(.005)
            self.assertTrue(client.get(url).json()['personas_locked'])
            self.assertEqual(len(client.get(url).json()['personas']),3)
            self.assertEqual(client.put(url+'/personas',json={'personas':[manual]}).status_code,409)
            self.assertEqual(client.post(url+'/personas/generate',json={'hint':'Too late'}).status_code,409)
            release.set()

    def test_run_reply_stream_and_reconnect(self):
        async def answer(*args, **kwargs):
            if 'questions' in (kwargs.get('structured') or {}).get('properties', {}): return json.dumps({'questions':[]})
            return 'A useful question or confirmed requirements'
        async def resolve(client):
            return 'http://localhost:11434'
        async def installed(client, url):
            return [{'name': 'test-model'}]
        app = FastAPI()
        app.include_router(create_workflow_router(answer, resolve, installed))
        body = {'goal': 'Test goal', 'agents': [{'id':'a','name':'Advisor','model':'test-model'}],
                'steps': [{'id':'s','title':'Clarify','kind':'clarify','agent_ids':['a']}]}
        with TestClient(app) as client:
            response = client.post('/api/workflow/runs', json=body)
            self.assertEqual(response.status_code, 200)
            run_id = response.json()['id']
            url = f'/api/workflow/runs/{run_id}'
            for _ in range(100):
                if client.get(url).json()['state'] == 'waiting_user':
                    break
                time.sleep(.005)
            self.assertEqual(client.get(url).json()['state'], 'waiting_user')
            self.assertEqual(client.post('/api/workflow/runs', json=body).status_code, 409)
            self.assertEqual(client.post(url+'/messages', json={'text':'My answer'}).status_code,200)
            for _ in range(100):
                if client.get(url).json()['state'] == 'completed':
                    break
                time.sleep(.005)
            self.assertEqual(client.get(url).json()['state'], 'completed')
            import json
            events = [json.loads(line) for line in client.get(url+'/events').text.splitlines()]
            self.assertTrue(any(e['type']=='deliverable' for e in events))
            cursor = events[-2]['seq']
            resumed = [json.loads(line) for line in client.get(url+f'/events?after={cursor}').text.splitlines()]
            self.assertEqual(len(resumed),1)
            self.assertEqual(resumed[0]['state'],'completed')
            self.assertEqual(client.post(url+'/messages', json={'text':'late'}).status_code,409)
            revised = {**body, 'revision': {'previous_result': 'Old result',
                                         'feedback': 'Make it more practical',
                                         'requirements': 'Already clarified'}}
            response = client.post('/api/workflow/runs', json=revised)
            self.assertEqual(response.status_code, 200)
            next_url = '/api/workflow/runs/' + response.json()['id']
            for _ in range(100):
                if client.get(next_url).json()['state'] == 'completed':
                    break
                time.sleep(.005)
            self.assertEqual(client.get(next_url).json()['state'], 'completed')
            events = [json.loads(line) for line in client.get(next_url+'/events').text.splitlines()]
            self.assertFalse(any(e.get('state')=='waiting_user' for e in events))
            self.assertTrue(any('Make it more practical' in e.get('content','') for e in events))

