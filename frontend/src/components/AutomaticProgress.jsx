import React from 'react';
import {Sparkles,Plus,SlidersHorizontal,LoaderCircle} from 'lucide-react';
import {ACTIVE} from '../lib/workflow';
import {t} from '../lib/i18n';

export default function AutomaticProgress({project,personaBusy,onAddPersona,onSettings}){
 const active=ACTIVE.includes(project.runState),options=project.optimization;
 const stage=!project.runId?t('progress.idle'):project.runState==='waiting_user'?t('progress.waiting'):project.runState==='completed'?t('progress.done'):project.personaGeneration==='running'?t('progress.personas'):project.cycleState==='reviewing'?t('progress.reviewing'):active?(project.cycle>0?t('progress.optimizing',{n:project.cycle}):t('progress.working')):t('progress.stopped');
 const count=options?.auto_generate?Math.max(options.persona_count||3,options.personas.length):options?.personas.length;
 return <section className="automatic-progress" aria-label={t('progress.label')}><div className="automatic-progress-heading"><span className="automatic-symbol">{active?<LoaderCircle className="spin" size={19}/>:<Sparkles size={19}/>}</span><div><h2>{stage}</h2><p>{options?.enabled?t('progress.auto',{count,rounds:options.rounds}):t('progress.manual')}{t('progress.local')}</p></div><button className="text-button" onClick={onSettings}><SlidersHorizontal size={14}/>{t('progress.settings')}</button></div>
 <div className="automatic-route"><span>{t('progress.confirm')}</span><i>→</i><span>{t('progress.discuss')}</span>{options?.enabled&&<><i>→</i><span>{t('progress.feedback')}</span></>}<i>→</i><span>{t('progress.delivery')}</span></div>
 {(options?.personas?.length>0||active&&options?.enabled)&&<div className="automatic-personas"><span>{t('progress.customers')}</span>{options.personas.map(p=><span className="automatic-persona-chip" key={p.id} title={p.profile}>{p.name}</span>)}{active&&!project.personasLocked&&<button className="text-button" disabled={personaBusy||options.personas.length>=4} onClick={()=>onAddPersona('')}><Plus size={13}/>{t('progress.addPersona')}</button>}{project.personaNotice&&<small role="status">{project.personaNotice}</small>}</div>}
 </section>
}
