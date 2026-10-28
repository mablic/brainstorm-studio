import React,{useEffect,useState} from 'react';
import {t} from '../lib/i18n';
import {SunMoon} from 'lucide-react';

export default function ThemeControl(){
 const [theme,setTheme]=useState(()=>{try{const saved=localStorage.getItem('brainstorm-theme');return ['light','dark'].includes(saved)?saved:'system'}catch{return 'system'}});
 useEffect(()=>{document.documentElement.dataset.theme=theme;try{localStorage.setItem('brainstorm-theme',theme)}catch{}},[theme]);
 return <label className="theme-control"><SunMoon size={14}/><select aria-label={t('theme.label')} value={theme} onChange={e=>setTheme(e.target.value)}><option value="system">{t('theme.system')}</option><option value="light">{t('theme.light')}</option><option value="dark">{t('theme.dark')}</option></select></label>;
}
