import {t} from './i18n.js';
export const SEARCH_ID = 'web-researcher';
const STEP_COLORS = {personas:'blue',feedback:'teal',clarify:'blue',research:'teal',discussion:'violet',summary:'orange',custom:'slate'};
const STEP_KINDS = Object.keys(STEP_COLORS);
export function stepTypes(){return Object.fromEntries(STEP_KINDS.map(kind=>[kind,{label:t(`step.${kind}.label`),description:t(`step.${kind}.description`),color:STEP_COLORS[kind],rules:t(`step.${kind}.rules`)}]));}
export const STEP_TYPES = new Proxy({},{get:(_,key)=>stepTypes()[key],ownKeys:()=>STEP_KINDS,getOwnPropertyDescriptor:(_,key)=>STEP_KINDS.includes(key)?{enumerable:true,configurable:true}:undefined});
export const STATUS = new Proxy({},{get:(_,key)=>t('status.'+key)});
export const ACTIVE = ['queued','running','waiting_user'];
export const uid = () => crypto.randomUUID();
export function createStep(kind='custom', agents=[]){return {id:uid(),title:STEP_TYPES[kind].label,kind,instructions:STEP_TYPES[kind].rules,agent_ids:agents,allow_web:['research','discussion'].includes(kind),rounds:2};}
export function blankProject(){return {id:uid(),goalDraft:'',autoMode:true,sharedResearchVersion:1,steps:[createStep('personas'),createStep('discussion'),createStep('summary'),createStep('feedback')],selectedStepId:null,runId:null,runState:'idle',lastSeq:0,conversations:[],outputs:[],sources:[],logs:[],activities:{},stepStates:{},result:null,depth:'decision',optimization:defaultOptimization(),versions:[],reviews:[],cycle:0,cycleState:'',revisionDraft:'',revisionNumber:1,error:'',createdAt:null};}
export function addAgent(steps, stepId, agentId){return steps.map(step=>{
  if(step.id!==stepId)return step;
  if(['clarify','personas'].includes(step.kind))return agentId===SEARCH_ID?step:{...step,agent_ids:[agentId]};
  if(step.agent_ids.includes(agentId)||step.agent_ids.length>=9)return step;
  return {...step,agent_ids:[...step.agent_ids,agentId],allow_web:agentId===SEARCH_ID?true:step.allow_web};
});}
export function removeStep(steps,id){return steps[0]?.id===id?steps:steps.filter(s=>s.id!==id);}
export function moveStep(steps,id,direction){const index=steps.findIndex(s=>s.id===id),next=index+direction;if(index<=0||next<=0||next>=steps.length)return steps;const copy=[...steps];[copy[index],copy[next]]=[copy[next],copy[index]];return copy;}
export function describeModel(name){
  const n=name.toLowerCase();
  const meta=(key,initials,accent)=>({initials,accent,specialty:t(`model.${key}.specialty`),description:t(`model.${key}.description`)});
  if(n.includes('qwen3.5'))return meta('qwen35','Q','blue');
  if(n.includes('qwen'))return meta('qwen','Q','indigo');
  if(n.includes('deepseek'))return meta('deepseek','D','violet');
  if(n.includes('llama'))return meta('llama','L','teal');
  if(n.includes('gemma'))return meta('gemma','G','orange');
  if(n.includes('phi'))return meta('phi','P','pink');
  return {initials:name[0]?.toUpperCase()||'A',accent:'slate',specialty:t('model.custom.specialty'),description:t('model.custom.description')};
}
export function preferredAgents(agents){const names=['qwen3.5:9b','qwen2.5:7b','llama3.1:8b','phi4-mini:3.8b','gemma2:9b'];return [...agents].sort((a,b)=>{const ai=names.indexOf(a.model),bi=names.indexOf(b.model);return (ai<0?99:ai)-(bi<0?99:bi);});}
// Allocation runs locally from step type, instructions and available member roles.
export function autoAssign(steps, agents){
 const available=agents.filter(a=>a.available!==false);
 if(!available.length)return steps;
 function rank(step){
  const task=step.title+' '+step.instructions;
  return available.map((a,index)=>{
   const n=a.model.toLowerCase(),role=(a.role||'')+' '+(a.specialty||'');
   let score=n.includes('qwen3.5')?90:n.includes('qwen2.5:7')?80:n.includes('qwen')?65:50;
   if(step.kind==='research')score+=/3b|4b|mini/.test(n)?30:0;
   if(step.kind==='discussion')score+=/deepseek|llama/.test(n)?20:0;
   if(a.size>8e9)score-=45;
   for(const word of ['创意','写作','内容','研究','资料','逻辑','分析','代码','技术','总结','整合','creative','writing','research','logic','analysis','code','technical','summary','delivery'])
    if(task.includes(word)&&role.includes(word))score+=25;
   return {a,score,index};
  }).sort((a,b)=>b.score-a.score||a.index-b.index).map(x=>x.a);
 }
 return steps.map(step=>{
  if(step.kind==='feedback')return step;
  const ranked=rank(step), chosen=[];
  if(step.kind==='discussion'){
   // Prefer diverse model families before adding a second member from a family.
   const families=new Set();
   for(const a of ranked){const name=a.model.toLowerCase();const family=['qwen','llama','deepseek','gemma','phi'].find(f=>name.includes(f))||name.split(':')[0];if(!families.has(family)){chosen.push(a);families.add(family)}if(chosen.length===3)break;}
   for(const a of ranked){if(chosen.length>=Math.min(3,ranked.length))break;if(!chosen.includes(a))chosen.push(a);}
  }else chosen.push(ranked[0]);
  return {...step,agent_ids:[...chosen.map(a=>a.id),...(step.allow_web&&!['clarify','personas'].includes(step.kind)?[SEARCH_ID]:[])]};
 });
}
export function revisionPayload(project,feedback){
 const previous=project.result?.content||project.outputs.at(-1)?.content;
 if(!previous||!feedback.trim())throw new Error(t('revision.need'));
 if(previous.length>60000)throw new Error(t('revision.long'));
 const latestBrief=[...project.conversations].reverse().find(m=>m.role==='assistant')?.content||'';
 const userNotes=project.conversations.filter(m=>m.role==='user'&&m.content!==project.goalDraft).map(m=>m.content).join('\n\n');
 const combined=t('revision.requirements',{prior:project.revision?.requirements||'',brief:latestBrief,notes:userNotes});
 const requirements=combined.length<=20000?combined:t('revision.trimmed',{brief:latestBrief.slice(0,9000),notes:userNotes.slice(-10000)});
 const sourceNotes=[...(project.revision?.evidence?[project.revision.evidence]:[]),...project.sources.map(s=>`[${s.id}] ${s.title} ${s.url}\n${(s.snippet||'').slice(0,200)}`)];
 let evidence=sourceNotes.join('\n');
 if(evidence.length>30000)evidence=evidence.slice(0,29500)+t('revision.evidenceTrim');
 const user_inputs=[...new Set([...(project.revision?.user_inputs||[]),...(project.revision?.feedback?[project.revision.feedback]:[]),...project.conversations.filter(m=>m.role==='user'&&m.content!==project.goalDraft).map(m=>m.content)])];
 if(user_inputs.length>100||user_inputs.reduce((n,x)=>n+x.length,0)>20000)throw new Error(t('revision.notes'));
 return {previous_result:previous,feedback:feedback.trim(),requirements,evidence,user_inputs};
}
export function validateProject(project,agents){if(project.depth==='decision'&&!['summary','feedback'].includes(project.steps.at(-1)?.kind))return t('validate.decision');if(project.optimization?.enabled){if(!['summary','feedback'].includes(project.steps.at(-1)?.kind))return t('validate.optEnd');if(!project.optimization.personas?.length&&!project.optimization.auto_generate)return t('validate.persona');for(const p of project.optimization.personas){if(!p.profile?.trim()||p.profile.trim().length<10)return t('validate.profile',{name:p.name});if(!agents.some(a=>a.id===p.agent_id&&a.available!==false))return t('validate.personaModel',{name:p.name});}}if(!project.goalDraft.trim())return t('validate.goal');const map=new Map(agents.map(a=>[a.id,a]));for(const [i,step]of project.steps.entries()){const members=step.agent_ids.filter(id=>id!==SEARCH_ID);if(!members.length&&step.kind!=='feedback'&&!(step.kind==='research'&&step.allow_web&&step.agent_ids.includes(SEARCH_ID)))return t('validate.member',{n:i+1,title:step.title});if(members.some(id=>!map.has(id)||map.get(id).available===false))return t('validate.offline',{n:i+1});}return '';}
export function exportMarkdown(project){const personas=(project.optimization?.personas||[]).map(p=>`- ${p.name}：${p.profile}`).join('\n');return [`# ${project.goalDraft||t('export.title')}`,t('export.version',{n:project.revisionNumber||1}),t('export.runState',{state:project.runState||t('status.idle')}),project.result?.content?t('export.conclusion',{content:project.result.content}):t('export.noConclusion'),project.error?t('export.error',{content:project.error}):'',project.optimization?.enabled?t('export.opt',{rounds:project.optimization.rounds,personas}):'',project.revision?t('export.revision',{feedback:project.revision.feedback,previous:project.revision.previous_result,evidence:project.revision.evidence||t('export.none')}):'',...project.conversations.map(m=>`## ${m.role==='user'?t('export.user'):m.agent||t('export.advisor')}\n\n${m.content}`),...project.outputs.map(m=>`## ${m.cycle>0?t('export.cycle',{n:m.cycle}):''}${m.title} · ${m.agent}\n\n${m.content}${m.tasks?.length?'\n\n'+t('export.tasks')+'\n'+m.tasks.map(q=>'- '+q).join('\n'):''}`),t('export.flow')+'\n\n'+JSON.stringify(project.steps.map(s=>({id:s.id,title:s.title,kind:s.kind,allow_web:s.allow_web,agent_ids:s.agent_ids})),null,2),...(project.logs||[]).filter(e=>e.type==='research_dispatch').map(e=>t('export.dispatch')+'\n\n'+JSON.stringify(e,null,2)),t('export.decision')+'\n\n'+JSON.stringify({decision:project.result?.decision,delivery_status:project.result?.delivery_status,decision_summary:project.result?.decision_summary,evidence_gaps:project.result?.evidence_gaps,stop_reason:project.result?.stop_reason},null,2),t('export.contract')+'\n\n'+JSON.stringify(project.taskContract||{},null,2),...(project.logs||[]).filter(e=>e.type==='step_return').map(e=>t('export.returned')+'\n\n'+JSON.stringify(e,null,2)),...(project.qualityChecks||[]).map(q=>t('export.check',{phase:q.phase})+'\n\n'+JSON.stringify(q,null,2)),...(project.logs||[]).filter(e=>['rejected_output','research_rejected'].includes(e.type)).map(e=>t('export.rejected')+'\n\n'+JSON.stringify(e,null,2)),t('export.sources')+'\n\n'+project.sources.map(s=>`- [${s.id}] [${s.title}](${s.url})\n  ${s.snippet}`).join('\n')].join('\n\n---\n\n');}
export function downloadText(name,text,type='text/markdown;charset=utf-8'){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}

export function exportFinalText(project){
 const result=project.result;
 if(!result?.content?.trim())throw new Error(t('final.missing'));
 const plain=text=>text.replace(/^#{1,6}\s+/gm,'').replace(/\[([^\]]+)\]\(([^)]+)\)/g,'$1（$2）').replace(/\*\*([^*]+)\*\*/g,'$1').replace(/`([^`]+)`/g,'$1');
 const parts=[t('final.title'),t('export.version',{n:project.revisionNumber||1}),t('final.goal',{goal:project.goalDraft||t('final.noGoal')})];
 if(result.incomplete)parts.push(t('final.incomplete'));
 else if(['suggest_validation','insufficient_evidence','not_recommended'].includes(result.decision))parts.push(t('final.decision',{label:t('final.'+result.decision)}));
 parts.push(plain(result.content));
 if(result.evidence_gaps?.length)parts.push(t('final.gaps')+'\n'+result.evidence_gaps.map(x=>'- '+x).join('\n'));
 return parts.join('\n\n').replace(/\r?\n/g,'\r\n');
}

export function defaultOptimization(){return {enabled:true,rounds:1,auto_generate:true,persona_count:3,personas:[]};}
export function assignPersonas(optimization,agents){const ranked=preferredAgents(agents.filter(a=>a.available!==false));return {...optimization,personas:optimization.personas.map((p,i)=>({...p,agent_id:ranked.some(a=>a.id===p.agent_id)?p.agent_id:ranked[i%Math.max(1,ranked.length)]?.id||''}))};}
export function decisionSteps(steps){const feedback=steps.find(s=>s.kind==='feedback');const result=steps.filter(s=>s.kind!=='feedback');if(!result.some(s=>s.kind==='discussion')){const step=createStep('discussion');const last=result.at(-1)?.kind==='summary'?result.length-1:result.length;result.splice(last,0,step)}if(result.at(-1)?.kind!=='summary')result.push(createStep('summary'));result.push(feedback||createStep('feedback'));return result;}

// Prepare the actual request at Start, so a fresh task requires no setup clicks.
export function prepareAutomaticProject(project,agents){
 const available=agents.filter(a=>a.available!==false);
 if(project.autoMode===false)return project;
 const original=project.steps.map((s,i)=>i===0&&s.kind==='clarify'?{...s,kind:'personas',title:STEP_TYPES.personas.label,instructions:s.instructions===STEP_TYPES.clarify.rules?STEP_TYPES.personas.rules:s.instructions}:s);
 const connected=project.sharedResearchVersion===1?original:original.map(s=>s.kind==='discussion'?{...s,allow_web:true,agent_ids:[...new Set([...s.agent_ids,SEARCH_ID])]}:s);
 const steps=decisionSteps(connected),assigned=autoAssign(steps,available),ids=new Set(available.map(a=>a.id));
 return {...project,sharedResearchVersion:1,steps:steps.map((s,i)=>s.agent_ids.some(id=>id!==SEARCH_ID)&&s.agent_ids.every(id=>id===SEARCH_ID||ids.has(id))?s:{...assigned[i],allow_web:s.allow_web}),optimization:assignPersonas(project.optimization||defaultOptimization(),available)};
}
