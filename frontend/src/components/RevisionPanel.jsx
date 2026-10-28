import React from 'react';
import {MessageSquarePlus,RotateCcw,LoaderCircle,Download} from 'lucide-react';
import {downloadText,exportFinalText} from '../lib/workflow';
import {t} from '../lib/i18n';

export default function RevisionPanel({project,setProject,sending,onRevise}){
 if(project.runState!=='completed'||!project.result?.content)return null;
 const draft=project.revisionDraft||'',version=project.revisionNumber||1;
 return <section className="panel revision-panel">
  <div className="panel-heading"><div className="section-title"><MessageSquarePlus size={17}/><h2>{t('revision.title')}</h2><span className="count-pill">{t('revision.version',{n:version})}</span></div><button type="button" className="primary-button" onClick={()=>downloadText(t('revision.file',{n:version}),'\uFEFF'+exportFinalText(project),'text/plain;charset=utf-8')}><Download size={15}/>{t('revision.download')}</button></div>
  <form className="revision-form" onSubmit={e=>{e.preventDefault();if(!sending&&draft.trim())onRevise(draft)}}>
   <label htmlFor="revision-feedback">{t('revision.ask')}</label>
   <textarea id="revision-feedback" aria-label={t('revision.feedback')} value={draft} maxLength={20000} disabled={sending} onChange={e=>setProject(p=>({...p,revisionDraft:e.target.value}))} placeholder={t('revision.placeholder')}/>
   <div className="revision-actions"><p>{t('revision.note')}</p><button type="submit" className="primary-button" disabled={sending||!draft.trim()}>{sending?<LoaderCircle size={15} className="spin"/>:<RotateCcw size={15}/>}{t('revision.run')}</button></div>
  </form>
 </section>
}
