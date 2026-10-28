import {useCallback,useEffect,useRef,useState} from 'react';
import {ACTIVE,SEARCH_ID,describeModel,addAgent,blankProject,autoAssign,revisionPayload,defaultOptimization,assignPersonas,prepareAutomaticProject,decisionSteps,preferredAgents,validateProject,uid} from '../lib/workflow';
import {getLang,t} from '../lib/i18n';
import {jsonRequest,post,readEvents} from '../lib/api';

const KEY='brainstorm-studio-v2';
function load(){try{return JSON.parse(localStorage.getItem(KEY)||'null')||{}}catch{return {}}}
export function useWorkspace(){
 const saved=useRef(load()).current;
 const [project,setProject]=useState(()=>{const loaded=saved.project?.steps?.length?{...blankProject(),...saved.project,sharedResearchVersion:saved.project.sharedResearchVersion,optimization:saved.project.optimization||defaultOptimization()}:blankProject();return !loaded.runId?prepareAutomaticProject(loaded,[]):loaded});
 const [connections,setConnections]=useState(saved.connections||[]),[overrides,setOverrides]=useState(saved.overrides||{}),[archives,setArchives]=useState(saved.archives||[]);
 const [agents,setAgents]=useState([]),[loading,setLoading]=useState(true),[serviceError,setServiceError]=useState(''),[storageError,setStorageError]=useState('');
 const [personaBusy,setPersonaBusy]=useState(false);
 const [connectionState,setConnectionState]=useState('idle'),[epoch,setEpoch]=useState(0),[sending,setSending]=useState(false);
 const cursor=useRef(0),terminal=useRef(false),projectRef=useRef(project);
 useEffect(()=>{projectRef.current=project},[project]);
 useEffect(()=>{try{localStorage.setItem(KEY,JSON.stringify({project,connections,overrides,archives}));setStorageError('')}catch{setStorageError(t('error.storage'))}},[project,connections,overrides,archives]);
 const refresh=useCallback(async()=>{setLoading(true);setServiceError('');const next=[];try{const data=await jsonRequest('/api/models');for(const m of data.models)next.push({id:`local::${m.name}`,name:m.name,model:m.name,size:m.size,base_url:null,source:t('agent.localOllama'),available:true});}catch(e){setServiceError(e.message)}
  const result=await Promise.allSettled(connections.map(async c=>{const data=await post('/api/workflow/connections/inspect',{base_url:c.base_url});return data.models.filter(m=>!c.models?.length||c.models.includes(m.name)).map(m=>({id:`${c.id}::${m.name}`,name:m.name,model:m.name,size:m.size,base_url:c.base_url,source:c.name,available:true}));}));
  result.forEach((r,i)=>{if(r.status==='fulfilled')next.push(...r.value);else for(const model of connections[i].models||[])next.push({id:`${connections[i].id}::${model}`,name:model,model,base_url:connections[i].base_url,source:connections[i].name,available:false});});
  setAgents(next);setLoading(false);
 },[connections]);
 useEffect(()=>{refresh()},[refresh]);
 const library=agents.map(a=>({...a,...overrides[a.id]}));
 useEffect(()=>{if(!agents.length)return;setProject(p=>{if(ACTIVE.includes(p.runState))return p;const optimization=assignPersonas(p.optimization||defaultOptimization(),agents);if(p.steps[0]?.agent_ids.length)return p.runId?{...p,optimization}:prepareAutomaticProject({...p,optimization},agents);const agent=preferredAgents(agents.filter(a=>a.available))[0];if(!agent)return p;const steps=[...p.steps];steps[0]={...steps[0],agent_ids:[agent.id]};return {...p,steps,optimization,selectedStepId:p.selectedStepId||steps[0].id};});},[agents]);
 const handleEvent=useCallback(event=>{if(!event.seq)return;cursor.current=Math.max(cursor.current,event.seq);if(event.type==='run_state')terminal.current=!ACTIVE.includes(event.state);setProject(p=>{if(p.runId!==event.run_id||event.seq<=p.lastSeq)return p;const next={...p,lastSeq:event.seq};
  if(event.type==='conversation')next.conversations=[...p.conversations,event];
  if(event.type==='work_output')next.outputs=[...p.outputs,event];
  if(event.type==='sources'){const ids=new Set(p.sources.map(s=>s.id));next.sources=[...p.sources,...event.sources.filter(s=>!ids.has(s.id)).map(s=>({...s,step_id:event.step_id,query:event.query}))];}
  if(event.type==='step_state')next.stepStates={...p.stepStates,[event.step_id]:event.state};
  if(event.type==='activity')next.activities={...p.activities,[`${event.step_id}:${event.agent_id}`]:event};
  if(event.type==='run_state')next.runState=event.state;
  if(event.type==='cycle_state'){next.cycle=event.cycle;next.cycleState=event.state;next.cycleTotal=event.total;}
  if(event.type==='version')next.versions=[...(p.versions||[]),event];
  if(event.type==='personas_updated'){next.optimization={...p.optimization,personas:event.personas};next.personasRevision=event.revision;next.personaNotice='';}
  if(event.type==='personas_locked')next.personasLocked=event.locked;
  if(event.type==='persona_request')next.personaNotice=event.content;
  if(event.type==='persona_generation')next.personaGeneration=event.state;
  if(event.type==='persona_feedback')next.reviews=[...(p.reviews||[]),event];
  if(event.type==='deliverable'||event.type==='delivery_checkpoint')next.result=event;
  if(event.type==='task_contract')next.taskContract=event.contract;
  if(event.type==='quality_check')next.qualityChecks=[...(p.qualityChecks||[]),event].slice(-150);
  if(event.type==='step_return')next.lastReturn=event;
  if(event.type==='error')next.error=event.content;
  if(!['conversation','work_output','sources'].includes(event.type))next.logs=[...p.logs,event].slice(-1000);
  return next;});},[]);
 useEffect(()=>{const id=project.runId;if(!id||!ACTIVE.includes(project.runState))return;const controller=new AbortController();cursor.current=project.lastSeq;terminal.current=false;let alive=true;
  (async()=>{for(let attempt=0;attempt<4&&alive;attempt++){try{setConnectionState(attempt?'reconnecting':'connected');await readEvents(`/api/workflow/runs/${id}/events?after=${cursor.current}`,controller.signal,handleEvent);if(terminal.current){setConnectionState('idle');return;}const state=await jsonRequest(`/api/workflow/runs/${id}`);if(!ACTIVE.includes(state.state)){setProject(p=>p.runId===id?{...p,runState:state.state,stepStates:state.step_states}:p);setConnectionState('idle');return;}}catch(e){if(e.name==='AbortError'||!alive)return;if(e.status===404){setProject(p=>p.runId===id?{...p,runState:'interrupted',error:e.message}:p);setConnectionState('offline');return;}if(attempt===3){setServiceError(t('error.stream'));setConnectionState('offline');return;}}await new Promise(resolve=>setTimeout(resolve,500*(attempt+1)));}})();
  return()=>{alive=false;controller.abort()};
  // State events update the UI; a stream remains attached until the run ID changes.
 },[project.runId,epoch,handleEvent]);
 function archiveCurrent(){const p=projectRef.current;if(p.conversations.length||p.outputs.length)setArchives(a=>[{...p,savedAt:Date.now()},...a.filter(x=>x.id!==p.id)].slice(0,8));}
 function newProject(){if(ACTIVE.includes(project.runState))return;archiveCurrent();const next=blankProject();const lead=preferredAgents(library.filter(a=>a.available))[0];if(lead)next.steps[0].agent_ids=[lead.id];next.optimization=assignPersonas(next.optimization,library);next.selectedStepId=next.steps[0].id;setProject(prepareAutomaticProject(next,library));setServiceError('');}
 async function start(revision=project.revision||null){if(ACTIVE.includes(project.runState)||sending)return false;if(loading){setProject(p=>({...p,error:t('error.connecting')}));return false;}if(!library.some(a=>a.available!==false)){setProject(p=>({...p,error:t('error.noModel')}));return false;}const prepared=prepareAutomaticProject(project,library);const problem=validateProject(prepared,library);if(problem){setProject(p=>({...p,error:problem}));return;}setSending(true);setServiceError('');try{const used=new Set(prepared.steps.flatMap(s=>s.agent_ids));if(prepared.optimization?.enabled)library.filter(a=>a.available!==false).forEach(a=>used.add(a.id));const body={goal:prepared.goalDraft,steps:prepared.steps,revision,depth:prepared.depth||'decision',language:getLang()==='en'?'en':'zh',optimization:prepared.optimization||defaultOptimization(),agents:library.filter(a=>used.has(a.id)).map(a=>({id:a.id,name:a.name,model:a.model,base_url:a.base_url,role:a.role||a.specialty||describeModel(a.model).description}))};const run=await post('/api/workflow/runs',body);archiveCurrent();cursor.current=0;terminal.current=false;setProject(p=>({...p,...prepared,id:uid(),revision,revisionDraft:'',revisionNumber:revision?(p.revisionNumber||1)+1:1,runId:run.id,runState:run.state,lastSeq:0,conversations:[],outputs:[],sources:[],versions:[],reviews:[],taskContract:null,qualityChecks:[],lastReturn:null,cycle:0,cycleState:'',personasLocked:false,personasRevision:0,personaGeneration:'',personaNotice:'',logs:[],activities:{},stepStates:run.step_states,result:null,error:'',createdAt:Date.now()}));return true;}catch(e){setProject(p=>({...p,error:e.message}));}finally{setSending(false)}}
 async function send(text){setSending(true);try{await post(`/api/workflow/runs/${project.runId}/messages`,{text});return true}catch(e){setProject(p=>({...p,error:e.message}));return false}finally{setSending(false)}}
 async function cancel(){try{await post(`/api/workflow/runs/${project.runId}/cancel`,{});}catch(e){setProject(p=>({...p,error:e.message}));}}
 return {project,setProject,personaBusy,agents:library,loading,sending,serviceError,storageError,connectionState,refresh,connections,archives,
  addConnection:connection=>setConnections(c=>[...c,{...connection,id:uid()}]),editAgent:(id,data)=>setOverrides(p=>({...p,[id]:data})),
  removeConnection:id=>setConnections(c=>c.filter(x=>x.id!==id)),newProject,start,send,cancel,reconnect:()=>{setServiceError('');setEpoch(e=>e+1)},
  savePersonas:async personas=>{setPersonaBusy(true);try{await jsonRequest(`/api/workflow/runs/${project.runId}/personas`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({personas})});return true}catch(e){setProject(p=>({...p,error:e.message}));return false}finally{setPersonaBusy(false)}},
  generatePersona:async hint=>{setPersonaBusy(true);try{await post(`/api/workflow/runs/${project.runId}/personas/generate`,{hint});return true}catch(e){setProject(p=>({...p,error:e.message}));return false}finally{setPersonaBusy(false)}},
  prepareDecision:()=>{if(ACTIVE.includes(project.runState)||sending)return;setProject(p=>({...p,steps:autoAssign(decisionSteps(p.steps),library)}))},
  autoAssign:()=>{if(ACTIVE.includes(project.runState)||sending)return;setProject(p=>({...p,steps:autoAssign(p.steps,library),optimization:assignPersonas(p.optimization||defaultOptimization(),library)}))},
  revise:async text=>{try{return await start(revisionPayload(project,text))}catch(e){setProject(p=>({...p,error:e.message}));return false}},
  addMember:(stepId,id)=>setProject(p=>({...p,steps:addAgent(p.steps,stepId,id)})),
  restore:archive=>{if(ACTIVE.includes(project.runState))return;archiveCurrent();setProject({...blankProject(),...archive,optimization:assignPersonas(archive.optimization||defaultOptimization(),library),runState:ACTIVE.includes(archive.runState)?'interrupted':archive.runState,error:''})},
  deleteArchive:id=>setArchives(items=>items.filter(item=>item.id!==id)),
  clearArchives:()=>setArchives([])};
}
