import React from 'react';
import {ShieldCheck,AlertCircle} from 'lucide-react';
import {t} from '../lib/i18n';

const DECISIONS=['suggest_validation','insufficient_evidence','not_recommended','unassessed'];
const ROUTES=['continue','research','clarify','discuss','rewrite'];
export default function TaskReview({project}){
 const checks=project.qualityChecks||[];
 const last=checks.at(-1),result=project.result,contract=project.taskContract;
 const route=project.lastReturn;
 if(!contract&&!last&&!result?.decision)return null;
 const warning=result?.decision==='insufficient_evidence'||result?.decision==='not_recommended'||last&&last.verdict!=='pass';
 const verdict=last?.verdict==='pass'?t('review.pass'):last?.verdict==='revise'?t('review.revise'):t('review.incomplete');
 const routeState=route?.state==='running'?t('review.running'):route?.state==='blocked'?t('review.blocked'):t('review.returned');
 return <div className={`task-review ${warning?'needs-attention':''}`}>
  <div className="task-review-title">{warning?<AlertCircle size={16}/>:<ShieldCheck size={16}/>}<strong>{result?.decision?(DECISIONS.includes(result.decision)?t('review.'+result.decision):result.decision):last?`${last.phase} · ${verdict}`:t('review.watch')}</strong><span>{t('review.cap')}</span></div>
  {result?.delivery_status==='provisional'&&<p><strong>{t('review.provisional')}</strong> {t('review.provisionalNote')}</p>}
  {result?.decision_summary&&<p>{result.decision_summary}</p>}
  {result?.evidence_gaps?.length>0&&<div><strong>{t('review.gaps')}</strong>{result.evidence_gaps.map((x,i)=><p key={i}>{x}</p>)}</div>}
  {result?.stop_reason&&<p>{result.stop_reason}</p>}
  {route&&<p><strong>{t('review.auto',{route:ROUTES.includes(route.action)?t('review.'+route.action):route.action,state:routeState})}</strong><br/>{route.content}</p>}
  {last?.verdict!=='pass'&&(last?.issues||[]).map((x,i)=><p key={i}>{x}</p>)}
  {contract&&<details><summary>{t('review.contract')}</summary><p><strong>{t('review.original')}</strong>{contract['原始任务']}</p>{contract['本轮真实修改要求']&&<p><strong>{t('review.change')}</strong>{contract['本轮真实修改要求']}</p>}{[...(contract['此前真实补充']||[]),...(contract['运行中真实补充']||[])].map((x,i)=><p key={i}><strong>{t('review.note')}</strong>{x}</p>)}<small>{contract['约束来源']}</small></details>}
  {checks.length>0&&<details><summary>{t('review.checks',{n:checks.length})}</summary>{checks.map(c=><p key={c.seq}><strong>{c.cycle>0?t('review.optCycle',{n:c.cycle}):t('review.first')}{c.phase}</strong>：{c.verdict==='pass'?t('review.passed'):c.verdict==='revise'?(ROUTES.includes(c.action)?t('review.'+c.action):t('review.revise')):t('review.unfinished')}{c.issues?.length?' · '+c.issues.join('；'):''}</p>)}</details>}
 </div>;
}
