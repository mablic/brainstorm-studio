import {test} from 'node:test';
import assert from 'node:assert/strict';
import {blankProject,createStep} from '../src/lib/workflow.js';
import {getLang,localizeSteps,setLang,t} from '../src/lib/i18n.js';

test('the page can switch between Chinese and English without rewriting custom steps',()=>{
 try{
  assert.equal(getLang(),'zh');
  const project=blankProject();
  assert.equal(project.steps[1].title,'团队讨论');
  project.steps[1].instructions='Keep this custom instruction';
  setLang('en');
  assert.equal(t('header.new'),'New task');
  const localized=localizeSteps(project.steps,'en');
  assert.equal(localized[0].title,'Generate user personas');
  assert.equal(localized[1].instructions,'Keep this custom instruction');
  assert.equal(localized[1].title,'Team discussion');
  assert.equal(createStep('summary').title,'Delivery');
 }finally{setLang('zh');}
});
