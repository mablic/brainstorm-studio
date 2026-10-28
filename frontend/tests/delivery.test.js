import {test} from 'node:test';
import assert from 'node:assert/strict';
import {blankProject,exportMarkdown} from '../src/lib/workflow.js';
test('export leads with retained conclusion and includes later failure',()=>{
 const p=blankProject();p.runState='failed';p.error='后续模型离线';
 p.result={content:'推荐：本地小工具，具体用途与取舍。',delivery_status:'provisional'};
 p.outputs=[{title:'讨论',agent:'顾问',content:'讨论细节'}];
 const text=exportMarkdown(p);
 assert.ok(text.includes(p.result.content));
 assert.ok(text.indexOf(p.result.content)<text.indexOf('讨论细节'));
 assert.ok(text.includes('运行状态：failed'));
 assert.ok(text.includes(p.error));
});
