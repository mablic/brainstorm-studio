import React,{useEffect,useState} from 'react';
import {UsersRound,Repeat2,Plus,Trash2,Layers} from 'lucide-react';
import {defaultOptimization,uid,ACTIVE} from '../lib/workflow';
import {t} from '../lib/i18n';
import Markdown from './Markdown';

export default function OptimizationPanel({project,setProject,agents,locked,onPrepare,onSavePersonas,onGeneratePersona,personaBusy}){
 const [draft,setDraft]=useState(null),[hint,setHint]=useState(''),[notice,setNotice]=useState('');
 useEffect(()=>{setDraft(null);setNotice('')},[project.runId]);
 useEffect(()=>{if(project.personasLocked&&draft&&!personaBusy){setDraft(null);setNotice(t('opt.lockedNotice'))}},[project.personasLocked,draft,personaBusy]);
 const options=draft||project.optimization||defaultOptimization();
 const live=ACTIVE.includes(project.runState)&&project.optimization?.enabled&&!project.personasLocked;
 const personaLocked=(locked&&!live)||personaBusy;
 async function save(){if(await onSavePersonas(options.personas))setDraft(null)}
 function patch(data){if(live){setDraft({...options,...data});return;}setProject(p=>({...p,optimization:{...(p.optimization||defaultOptimization()),...data}}))}
 function persona(id,data){patch({personas:options.personas.map(p=>p.id===id?{...p,...data}:p)})}
 const label=project.cycleState==='reviewing'?t('opt.reviewing'):project.cycleState==='working'?t('opt.working'):t('opt.roundDone');
 return <section className="panel optimization-panel">
  <div className="panel-heading"><div className="section-title"><UsersRound size={17}/><h2>{t('opt.title')}</h2><span className="count-pill">{t('opt.local')}</span></div><label className="optimization-switch"><input type="checkbox" checked={options.enabled} disabled={locked} onChange={e=>patch({enabled:e.target.checked})}/>{t('opt.enable')}</label></div>
  <div className="optimization-body">
   <div className="decision-controls"><label>{t('opt.depth')}<select aria-label={t('opt.depth')} value={project.depth||'decision'} disabled={locked} onChange={e=>setProject(p=>({...p,depth:e.target.value}))}><option value="decision">{t('opt.decision')}</option><option value="standard">{t('opt.standard')}</option></select></label><button className="secondary-button" disabled={locked||!agents.length||project.steps.length>10} onClick={onPrepare}><Layers size={14}/>{t('opt.prepare')}</button></div>
   <p className="optimization-note">{t('opt.note')}</p>
   {!['summary','feedback'].includes(project.steps.at(-1)?.kind)&&<p className="optimization-note">{t('opt.needEnd')}</p>}
   {options.enabled&&<><div className="optimization-rounds"><label><Repeat2 size={15}/>{t('opt.rounds')}<select aria-label={t('opt.rounds')} value={options.rounds} disabled={locked} onChange={e=>patch({rounds:+e.target.value})}>{[1,2,3,4,5].map(n=><option value={n} key={n}>{t('opt.roundN',{n})}</option>)}</select></label><span>{t('opt.roundNote',{rounds:options.rounds,total:options.rounds+1})}</span></div>
   <div className="persona-auto-settings"><label><input type="checkbox" checked={!!options.auto_generate} disabled={locked} onChange={e=>patch({auto_generate:e.target.checked})}/>{t('opt.autoPersona')}</label>{options.auto_generate&&<label>{t('opt.count')}<select aria-label={t('opt.count')} value={options.persona_count||3} disabled={locked} onChange={e=>patch({persona_count:+e.target.value})}>{[1,2,3,4].map(n=><option key={n} value={n}>{t('opt.countN',{n})}</option>)}</select></label>}<p className="optimization-note">{t('opt.autoNote')}</p></div>
   {notice&&<p className="optimization-note" role="status">{notice}</p>}
   {project.personaNotice&&<p className="optimization-note" role="status">{project.personaNotice}</p>}
   {!locked&&options.personas.length>0&&<button className="text-button" onClick={()=>patch({personas:[],auto_generate:true})}>{t('opt.regenerate')}</button>}
   {project.personaGeneration==='running'&&<p role="status">{t('opt.generating')}</p>}
   {live&&<p className="optimization-note">{t('opt.live')}</p>}
   {project.personasLocked&&locked&&<p className="optimization-note">{t('opt.locked')}</p>}
   <details className="persona-settings" open={!locked||live}><summary>{t('opt.configure',{n:options.personas.length})}</summary><div className="persona-grid">{options.personas.map(p=><article className="persona-card" key={p.id}><div><span className="simulated-tag">{t('opt.sim')}</span><button className="icon-button" aria-label={t('opt.delete',{name:p.name})} disabled={personaLocked||options.personas.length===1} onClick={()=>patch({personas:options.personas.filter(x=>x.id!==p.id)})}><Trash2 size={13}/></button></div><label>{t('opt.name')}<input aria-label={`${t('opt.name')} ${p.id}`} value={p.name} maxLength={100} disabled={personaLocked} onChange={e=>persona(p.id,{name:e.target.value})}/></label><label>{t('opt.model')}<select aria-label={`${t('opt.model')} ${p.id}`} value={p.agent_id} disabled={personaLocked} onChange={e=>persona(p.id,{agent_id:e.target.value})}><option value="">{t('opt.pickModel')}</option>{agents.filter(a=>a.available!==false).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label><label>{t('opt.profile')}<textarea aria-label={`${t('opt.profile')} ${p.id}`} value={p.profile} minLength={10} maxLength={4000} disabled={personaLocked} onChange={e=>persona(p.id,{profile:e.target.value})}/></label></article>)}</div>
   <button className="text-button" disabled={personaLocked||options.personas.length>=4} onClick={()=>patch({personas:[...options.personas,{id:uid(),name:t('opt.customName'),profile:t('opt.customProfile'),agent_id:agents.find(a=>a.available!==false)?.id||''}]})}><Plus size={14}/>{t('opt.addManual')}</button>
   {live&&<div className="persona-live-actions"><input aria-label={t('opt.hint')} placeholder={t('opt.hintPlaceholder')} value={hint} maxLength={2000} disabled={personaBusy} onChange={e=>setHint(e.target.value)}/><button className="secondary-button" disabled={personaBusy||options.personas.length>=4} onClick={async()=>{if(await onGeneratePersona(hint))setHint('')}}><Plus size={14}/>{t('opt.addAuto')}</button>{draft&&<button className="primary-button" disabled={personaBusy||!options.personas.length} onClick={save}>{t('opt.save')}</button>}</div>}
   {!options.personas.length&&<p className="optimization-note">{t('opt.empty')}</p>}
   </details>
   </>}
   {project.cycleState&&<div className="cycle-progress"><Repeat2 size={15}/>{project.cycle===0?t('opt.firstVersion'):t('opt.optRound',{n:project.cycle})} · {label}{project.runState==='completed'?t('opt.finished'):''}</div>}
   {(project.versions||[]).length>0&&<div className="version-history"><h3>{t('opt.history')}</h3>{project.versions.map(v=><details key={v.seq}><summary>{v.cycle===0?t('opt.v0'):t('opt.vN',{n:v.cycle})} · {t('opt.feedbackCount',{n:(project.reviews||[]).filter(r=>r.cycle===v.cycle).length})}</summary><div className="markdown"><Markdown>{v.content}</Markdown></div>{(project.reviews||[]).filter(r=>r.cycle===v.cycle).map(r=><div className="persona-review" key={r.seq}><strong>{r.persona} · {t('opt.simFeedback')}</strong><small>{r.model}</small><div className="markdown"><Markdown>{r.content}</Markdown></div></div>)}</details>)}</div>}
  </div>
 </section>
}
