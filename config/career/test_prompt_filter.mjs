import test from 'node:test';
import assert from 'node:assert/strict';
import {assessFilter,parseBatch,restoreFilter,clearFilter,unassessedCount} from './prompt-filter.mjs';
import {filtered} from './model.mjs';
const job=(id,title='Senior Data Scientist')=>({id,title,company:'Example',location:'London',lifecycle:'active',status:'unseen',evidence_hash:'v1'});
const jobs=[job('a'),job('b','Demand planning analyst'),job('c','Frontend engineer')];
const response=rows=>({stopReason:'stop',content:[{type:'text',text:JSON.stringify({results:rows})}],usage:{cost:{total:0.01}}});
const rows=[{id:'a',level:'direct',reason:'Time-series forecasting is explicit.'},{id:'b',level:'tangential',reason:'Capacity planning is a related decision problem.'},{id:'c',level:'none',reason:''}];
const snapshot={jobs,inventory_updated_at:'2026-10-07'};
test('semantic matches include tangential roles, compose with board filters, and never alter status',async()=>{
 const before=structuredClone(jobs);
 const filter=await assessFilter(snapshot,'forecasting, even tangential',async()=>response(rows));
 assert.deepEqual(filtered(jobs,'Discover','','All roles',filter).map(x=>x.id),['a','b']);
 assert.deepEqual(filtered(jobs,'Discover','demand','All roles',filter).map(x=>x.id),['b']);
 assert.deepEqual(filtered(jobs,'Discover','','Data science',filter).map(x=>x.id),['a']);
 assert.deepEqual(jobs,before);
 const moved=[{...jobs[0],status:'shortlisted'},...jobs.slice(1)];
 assert.equal(filtered(moved,'Shortlist','','All roles',filter)[0].id,'a');
});
test('unknown, missing, duplicate IDs and malformed results cannot publish',()=>{
 for(const bad of [rows.slice(1),[rows[0],rows[0],rows[2]],[{...rows[0],id:'x'},...rows.slice(1)],[{...rows[0],level:'perfect'},...rows.slice(1)]]) {
  assert.throws(()=>parseBatch(JSON.stringify({results:bad}),jobs));
 }
 assert.throws(()=>parseBatch('not json',jobs));
});
test('late completion after cancellation cannot return a filter',async()=>{
 const controller=new AbortController();let finish;
 const pending=assessFilter(snapshot,'forecasting',()=>new Promise(resolve=>finish=resolve),controller.signal);
 controller.abort(); finish(response(rows));
 await assert.rejects(pending,/cancelled/);
});
test('later batch failure does not publish partial results or mutate previous filter',async()=>{
 const previous=await assessFilter(snapshot,'forecasting',async()=>response(rows));const before=structuredClone(previous);
 const many=Array.from({length:25},(_,i)=>job(String(i)));let call=0;
 await assert.rejects(()=>assessFilter({jobs:many},'new prompt',async(context)=>{
  call++;if(call===2)throw new Error('Network failed');
  const batch=JSON.parse(context.messages[0].content[0].text).jobs;
  return response(batch.map(j=>({id:j.id,level:'direct',reason:'Evidence supports it.'})));
 }),/Network/);
 assert.deepEqual(previous,before);
});
test('clear retains prompt; empty matches clear back to full view; reassess uses new corpus',async()=>{
 const none=await assessFilter(snapshot,'unrelated',async()=>response(rows.map(r=>({...r,level:'none',reason:''}))));
 assert.equal(filtered(jobs,'Discover','','All roles',none).length,0);
 const cleared=clearFilter(none);assert.equal(cleared.prompt,'unrelated');
 assert.equal(filtered(jobs,'Discover','','All roles',cleared).length,3);
 const changed=[...jobs,job('new')];assert.equal(unassessedCount(changed,none),1);
 assert.equal(unassessedCount([{...jobs[0],evidence_hash:'v2'},...jobs.slice(1)],none),1);
 const rerun=await assessFilter({jobs:changed},none.prompt,async()=>response([...rows,{id:'new',level:'uncertain',reason:'Description is missing; relationship unconfirmed.'}]));
 assert.equal(unassessedCount(changed,rerun),0);assert.ok(rerun.matches.new);
});
test('session restoration accepts validated complete state and rejects malformed state',async()=>{
 const value=await assessFilter(snapshot,'forecasting',async()=>response(rows));
 assert.deepEqual(restoreFilter(JSON.parse(JSON.stringify(value))),value);
 for(const bad of [null,{}, {...value,matches:[]}, {...value,assessed:{a:3}}, {...value,matches:{x:rows[0]}}, {...value,matches:{a:{level:'none',reason:''}}}]) assert.equal(restoreFilter(bad),null);
});
test('new and resumed sessions cannot inherit another session filter',async()=>{
 const {restoreSessionView}=await import('./prompt-filter.mjs');
 const filter=await assessFilter(snapshot,'forecasting',async()=>response(rows));
 const a=restoreSessionView([{type:'custom',customType:'career-view',data:{tab:1,index:0,query:'London',semantic:filter}}]);
 assert.equal(a.semantic.prompt,'forecasting');
 assert.equal(restoreSessionView([]).semantic,null);
 assert.equal(restoreSessionView([{type:'custom',customType:'unrelated',data:a}]).semantic,null);
 const b=restoreSessionView([{type:'custom',customType:'career-view',data:{tab:0,query:'',semantic:clearFilter(filter)}}]);
 assert.equal(b.semantic.active,false);assert.equal(b.semantic.prompt,'forecasting');
 assert.equal(a.semantic.active,true);
});

test('malformed assessment retries only its batch once and requires exact complete replacement',async()=>{
 for(const bad of [null,{}, {results:rows.slice(1)}, {results:[rows[0],rows[0],rows[2]]}, {results:[{...rows[0],id:'unknown'},...rows.slice(1)]}, {results:[{...rows[0],reason:''},...rows.slice(1)]}, 'broken']) {
  let calls=0;
  const filter=await assessFilter(snapshot,'forecasting',async context=>{
   calls++;
   if(calls===1)return {stopReason:'stop',content:[{type:'text',text:bad==='broken'?'broken':JSON.stringify(bad)}]};
   assert.match(context.messages[1].content[0].text,/complete replacement JSON/);
   assert.deepEqual(JSON.parse(context.messages[0].content[0].text).jobs,jobs);
   return response(rows);
  });
  assert.equal(calls,2);assert.deepEqual(Object.keys(filter.matches),['a','b']);
 }
 let calls=0;
 await assert.rejects(()=>assessFilter(snapshot,'x',async()=>{calls++;return response([]);}),/Full assessment invalid after one corrective retry:.*missing 3/);
 assert.equal(calls,2);
});
test('assessment transport, cancellation and incomplete responses never retry',async()=>{
 for(const kind of ['transport','cancel','length','error','aborted','toolUse']) {
  let calls=0;const controller=new AbortController();
  await assert.rejects(()=>assessFilter(snapshot,'x',async()=>{
   calls++;if(kind==='transport')throw new Error('network failed');
   if(kind==='cancel'){controller.abort();return response([]);}
   return {stopReason:kind,content:[{type:'text',text:'bad'}]};
  },controller.signal),kind==='transport'?/network/:kind==='cancel'?/cancelled/:/did not finish/);
  assert.equal(calls,1);
 }
});
test('late corrective completion after cancellation cannot publish results',async()=>{
 let calls=0;const controller=new AbortController();
 await assert.rejects(()=>assessFilter(snapshot,'x',async()=>{
  calls++;if(calls===1)return response([]);
  controller.abort();return response(rows);
 },controller.signal),/cancelled/);
 assert.equal(calls,2);
});

test('live Luna regression: concatenated JSON with stray characters requires one complete replacement',async()=>{
 // Sanitized structure of the real 314-listing live run's malformed assessment:
 // a complete results object, stray quote/braces, then another results object.
 const valid=JSON.stringify({results:rows});
 const malformed=valid+'"}"}'+valid;
 assert.throws(()=>parseBatch(malformed,jobs),/not valid JSON/);
 let calls=0;
 const filter=await assessFilter(snapshot,'forecasting',async context=>{
  calls++;
  if(calls===1)return {stopReason:'stop',content:[{type:'text',text:malformed}]};
  assert.match(context.messages[1].content[0].text,/not valid JSON/);
  return response(rows);
 });
 assert.equal(calls,2);assert.deepEqual(Object.keys(filter.matches),['a','b']);
 assert.deepEqual(Object.keys(filter.assessed),['a','b','c']);
});
