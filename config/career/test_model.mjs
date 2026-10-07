import test from 'node:test';
import assert from 'node:assert/strict';
import {filtered,capability,safeUrl,clean} from './model.mjs';
const job=(id,title,status='unseen',lifecycle='active')=>({id,title,status,lifecycle,company:'Example',location:'London',score:90});
test('discovery promotes Senior DS above old ML score and filters each destination',()=>{
 const rows=[job('ml','Senior Machine Learning Engineer'),{...job('ds','Senior Data Scientist'),score:60},job('saved','Data Scientist','shortlisted'),job('applied','Senior Data Scientist','applied'),job('closed','Senior Data Scientist','unseen','expired')];
 assert.deepEqual(filtered(rows,'Discover').map(j=>j.id),['ds','ml']);
 assert.deepEqual(filtered(rows,'Shortlist').map(j=>j.id),['saved']);
 assert.deepEqual(filtered(rows,'Applications').map(j=>j.id),['applied']);
 assert.equal(filtered(rows,'Discover','example london','Data science').length,1);
});
test('applied history and expired roles cannot be casually advanced or downgraded',()=>{
 assert.ok(capability(job('a','DS','applied'),'dismissed'));
 assert.ok(capability(job('a','DS','applied'),'shortlisted'));
 assert.ok(capability(job('a','DS','unseen','expired'),'draft'));
 assert.equal(capability(job('a','DS','applied'),'draft'),null);
 assert.equal(capability(job('a','DS'),'shortlisted'),null);
});
test('saved inactive roles remain reviewable and URLs/control sequences are bounded',()=>{
 assert.equal(filtered([job('x','DS','shortlisted','expired')],'Shortlist').length,1);
 assert.equal(safeUrl('file:///etc/passwd'),null);
 assert.equal(safeUrl('https://user:password@example.com'),null);
 assert.equal(safeUrl('https://example.com/jobs/1'),'https://example.com/jobs/1');
 assert.equal(clean('a\x1bb\nc'),'a b c');
});

test('committed status remains available when inventory reload fails',async()=>{
 const {saveAndReload}=await import('./model.mjs');
 const saved={committed:true,job:job('a','DS','shortlisted')};
 const outcome=await saveAndReload(async()=>saved,async()=>{throw new Error('Inventory temporarily unreadable');});
 assert.equal(outcome.saved.job.status,'shortlisted');
 assert.match(outcome.refreshError,/Inventory/);
 assert.equal(outcome.data,undefined);
});
test('failed projection repair does not prevent authoritative data reload',async()=>{
 const {repairAndReload}=await import('./model.mjs');
 const data={jobs:[job('a','DS','shortlisted')]};
 const outcome=await repairAndReload(async()=>{throw new Error('Board is unwritable');},async()=>data);
 assert.equal(outcome.data,data);
 assert.match(outcome.warning,/unwritable/);
});
