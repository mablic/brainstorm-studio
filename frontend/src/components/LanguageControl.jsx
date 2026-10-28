import React, { useEffect, useState } from 'react';
import { getLang, setLang, subscribe, t } from '../lib/i18n';

export function useI18n() {
  const [lang, set] = useState(getLang);
  useEffect(() => subscribe(set), []);
  return { lang, setLang, t };
}

export default function LanguageControl({ onChange }) {
  const { lang } = useI18n();
  return <div className="language-switch" role="group" aria-label={t('lang.label')}>
    <button type="button" className={lang === 'zh' ? 'active' : ''} aria-pressed={lang === 'zh'} onClick={() => (onChange || setLang)('zh')}>{t('lang.zh')}</button>
    <button type="button" className={lang === 'en' ? 'active' : ''} aria-pressed={lang === 'en'} onClick={() => (onChange || setLang)('en')}>{t('lang.en')}</button>
  </div>;
}
