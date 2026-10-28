import {test} from 'node:test';
import assert from 'node:assert/strict';
import {blankProject,createStep,addAgent,removeStep,moveStep,autoAssign,revisionPayload,exportMarkdown,validateProject,SEARCH_ID,defaultOptimization,assignPersonas,decisionSteps,prepareAutomaticProject} from '../src/lib/workflow.js';

test('default is a complete automatic workflow with protected clarification',()=>{
 const p=blankProject();assert.equal(p.steps.length,4);assert.equal(p.optimization.enabled,true);assert.equal(p.optimization.auto_generate,true);assert.equal(p.steps[0].kind,'personas');
 assert.deepEqual(removeStep(p.steps,p.steps[0].id),p.steps);
 assert.deepEqual(moveStep(p.steps,p.steps[0].id,1),p.steps);
 const assigned=addAgent(p.steps,p.steps[0].id,'a');
 assert.deepEqual(addAgent(assigned,p.steps[0].id,'b')[0].agent_ids,['b']);
 assert.deepEqual(addAgent(assigned,p.steps[0].id,SEARCH_ID),assigned);
});
test('multiple members, web permission and safe reordering',()=>{
 const first=createStep('clarify'),second=createStep('discussion'),third=createStep('summary');
 let steps=[first,second,third];steps=addAgent(steps,second.id,'a');steps=addAgent(steps,second.id,'b');steps=addAgent(steps,second.id,SEARCH_ID);
 assert.equal(steps[1].agent_ids.length,3);assert.equal(steps[1].allow_web,true);
 assert.equal(moveStep(steps,second.id,-1)[0].id,first.id);
 assert.equal(moveStep(steps,third.id,-1)[1].id,third.id);
});
test('allocation uses available models, diverse discussion and existing web permissions',()=>{
 const agents=[{id:'q',model:'qwen3.5:9b'},{id:'small',model:'qwen2.5:3b'},
  {id:'l',model:'llama3.1:8b'},{id:'d',model:'deepseek-r1:8b'},{id:'offline',model:'qwen3.5:9b',available:false}];
 const p=blankProject();p.goalDraft='A useful task';p.steps=[p.steps[0],createStep('discussion'),createStep('research'),createStep('summary')];
 const original=JSON.stringify(p.steps);const steps=autoAssign(p.steps,agents);
 assert.equal(JSON.stringify(p.steps),original);assert.equal(steps[0].agent_ids.length,1);
 assert.equal(steps[1].agent_ids.filter(id=>id!==SEARCH_ID).length,3);assert.equal(steps[1].allow_web,true);
 assert.ok(steps[2].agent_ids.includes(SEARCH_ID));assert.equal(steps[2].agent_ids[0],'small');
 assert.ok(steps.every(s=>!s.agent_ids.includes('offline')));
 assert.equal(validateProject({...p,steps},agents),'');assert.match(validateProject({...p,steps},[]),/不可用/);
 assert.deepEqual(autoAssign(p.steps,[]),p.steps);
});
test('revision preserves prior result, user constraints, feedback and source references',()=>{
 const p=blankProject();p.goalDraft='Original goal';p.result={content:'Previous recommendation [Rold-W2]'};
 p.conversations=[{role:'user',content:'budget 100'},{role:'assistant',content:'Confirmed requirements'}];
 p.sources=[{id:'Rold-W2',title:'Source',url:'https://example.com',snippet:'Evidence'}];
 const revision=revisionPayload(p,' Reduce cost ');
 assert.equal(revision.feedback,'Reduce cost');assert.equal(revision.previous_result,p.result.content);
 assert.match(revision.requirements,/budget 100/);assert.match(revision.evidence,/https:\/\/example.com/);
 assert.throws(()=>revisionPayload(p,'   '));
 assert.match(exportMarkdown({...p,revision,revisionNumber:2}),/Reduce cost/);
});
test('allocation recognizes alternate llama model names as the same family',()=>{
 const agents=[{id:'q',model:'qwen3.5:9b'},{id:'l',model:'llama3.1:8b'},
 {id:'l2',model:'vendor/llama3-chinese:latest',size:8.5e9},{id:'d',model:'deepseek-r1:8b'}];
 const [step]=autoAssign([createStep('discussion')],agents);
 assert.deepEqual(step.agent_ids,['q','l','d',SEARCH_ID]);
});
test('large revision notes are bounded without dropping the final result or latest feedback',()=>{
 const p=blankProject();p.result={content:'Full final result'};
 p.conversations=[{role:'assistant',content:'x'.repeat(40000)},{role:'user',content:'Newest constraint'},{role:'assistant',content:'Confirmed brief'}];
 p.sources=Array.from({length:200},(_,i)=>({id:i,title:'a'.repeat(200),url:'https://example.com',snippet:'x'.repeat(500)}));
 const revision=revisionPayload(p,'Critical feedback');assert.ok(revision.requirements.length<=20000);
 assert.ok(revision.evidence.length<=30000);assert.match(revision.requirements,/Newest constraint/);
 assert.equal(revision.previous_result,'Full final result');
});
test('personas reuse available local models and preserve explicit choices',()=>{
 const config={...defaultOptimization(),personas:[{id:'p',name:'Test',profile:'Specific user profile',agent_id:''}]};assert.equal(defaultOptimization().personas.length,0);assert.equal(defaultOptimization().auto_generate,true);
 const agents=[{id:'a',model:'qwen3.5:9b'},{id:'b',model:'llama3.1:8b'}];
 const assigned=assignPersonas(config,agents);assert.ok(assigned.personas.every(p=>['a','b'].includes(p.agent_id)));
 assigned.personas[0].agent_id='b';assert.equal(assignPersonas(assigned,agents).personas[0].agent_id,'b');
 assert.ok(config.personas.every(p=>p.agent_id===''));
});
test('decision preparation retains instructions and ends in delivery without duplicate stages',()=>{
 const p=blankProject();p.steps[0].instructions='Preserve my custom instructions';
 const steps=decisionSteps(p.steps);assert.equal(steps.length,4);assert.equal(steps.at(-1).kind,'feedback');
 assert.equal(steps[0].instructions,'Preserve my custom instructions');
 assert.equal(decisionSteps(steps).length,4);
 p.goalDraft='Test';p.steps=autoAssign(steps,[{id:'a',model:'qwen:7b'}]);
 p.optimization=assignPersonas({...defaultOptimization(),enabled:true},[{id:'a',model:'qwen:7b'}]);
 assert.equal(validateProject(p,[{id:'a',model:'qwen:7b'}]),'');
 p.steps=p.steps.slice(0,1);assert.match(validateProject(p,[{id:'a',model:'qwen:7b'}]),/成果交付/);
});

test('fresh goal starts without choosing steps, members or checkboxes',()=>{
 const p=blankProject();p.goalDraft='Find a differentiated app idea for young adults';
 const agents=[{id:'a',model:'qwen3.5:9b',available:true}];
 const ready=prepareAutomaticProject(p,agents);
 assert.equal(validateProject(ready,agents),'');
 assert.deepEqual(ready.steps.map(s=>s.kind),['personas','discussion','summary','feedback']);
 assert.ok(ready.steps.filter(s=>s.kind!=='feedback').every(s=>s.agent_ids.includes('a')));
 assert.equal(ready.optimization.enabled,true);assert.equal(ready.optimization.persona_count,3);
 assert.ok(ready.steps.filter(s=>s.kind!=='discussion').every(s=>s.allow_web===false));
 assert.equal(ready.steps.find(s=>s.kind==='discussion').allow_web,true);
 assert.ok(p.steps.some(s=>s.agent_ids.length===0));
});
test('automatic preparation preserves manual instructions and valid explicit assignments',()=>{
 const p=blankProject();p.steps[1].instructions='Compare against my incumbent product';p.steps[1].agent_ids=['b'];
 const agents=[{id:'a',model:'qwen3.5:9b'},{id:'b',model:'llama3.1:8b'}];
 const ready=prepareAutomaticProject(p,agents);assert.deepEqual(ready.steps[1].agent_ids,['b']);
 assert.equal(ready.steps[1].instructions,'Compare against my incumbent product');
 p.autoMode=false;p.steps=[p.steps[0]];assert.equal(prepareAutomaticProject(p,agents).steps.length,1);
});

test('legacy automatic flows connect research once and preserve later manual disabling',()=>{
 const p=blankProject();delete p.sharedResearchVersion;p.steps[1].allow_web=false;
 const agents=[{id:'a',model:'qwen3.5:9b'}];
 const migrated=prepareAutomaticProject(p,agents);
 assert.equal(migrated.steps[1].allow_web,true);assert.ok(migrated.steps[1].agent_ids.includes(SEARCH_ID));
 migrated.steps[1].allow_web=false;migrated.steps[1].agent_ids=['a'];
 const next=prepareAutomaticProject(migrated,agents);assert.equal(next.steps[1].allow_web,false);
 assert.ok(!next.steps[1].agent_ids.includes(SEARCH_ID));
});
