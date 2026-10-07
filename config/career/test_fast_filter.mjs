import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readdir, writeFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fastFilter,diskCache} from './fast-filter.mjs';
const jobs=['a','b','c'].map(id=>({id,title:id,company:'Example',description:'Evidence '+id,evidence_hash:'v1',status:'unseen',lifecycle:'active'}));
const snapshot={jobs};
const response=data=>({stopReason:'stop',content:[{type:'text',text:JSON.stringify(data)}]});
function setup() {
 const store=new Map(),calls=[];
 const cache={get:async k=>structuredClone(store.get(JSON.stringify(k))),set:async(k,v)=>store.set(JSON.stringify(k),structuredClone(v))};
 const complete=async context=>{
  const body=JSON.parse(context.messages[0].content[0].text);
  if(context.systemPrompt.startsWith('Summarise')) {calls.push(['summary',body.jobs.map(j=>j.id)]);return response({summaries:body.jobs.map(j=>({id:j.id,summary:j.description || 'Missing evidence.'}))});}
  if(context.systemPrompt.startsWith('Select')) {calls.push(['select',body.jobs.map(j=>j.id)]);return response({candidates:body.jobs.filter(j=>j.id!=='c').map(j=>j.id)});}
  calls.push(['detail',body.jobs.map(j=>j.id)]);
  return response({results:body.jobs.map(j=>({id:j.id,level:j.id==='b'?'uncertain':'tangential',reason:'Evidence-based explanation.'}))});
 };
 return {cache,calls,complete};
}
test('quick search screens once, checks only candidates, caches repeats and shares summaries across prompts',async()=>{
 const {cache,calls,complete}=setup(),options={cache,model:'luna'};
 const first=await fastFilter(snapshot,'forecasting',complete,undefined,undefined,options);
 assert.deepEqual(calls,[['summary',['a','b','c']],['select',['a','b','c']],['detail',['a','b']]]);
 assert.deepEqual(Object.keys(first.matches),['a','b']);assert.equal(first.matches.b.level,'uncertain');
 assert.equal(first.mode,'quick');
 calls.length=0;
 assert.deepEqual(await fastFilter(snapshot,'forecasting',complete,undefined,undefined,options),first);
 assert.equal(calls.length,0);
 await fastFilter(snapshot,'planning',complete,undefined,undefined,options);
 assert.deepEqual(calls,[['select',['a','b','c']],['detail',['a','b']]]);
});
test('actual evidence changes invalidate summaries and detail even with same tracker hash',async()=>{
 const {cache,calls,complete}=setup(),options={cache,model:'luna'};
 await fastFilter(snapshot,'forecasting',complete,undefined,undefined,options);calls.length=0;
 await fastFilter({jobs:jobs.map(j=>j.id==='a'?{...j,description:'New description'}:j)},'forecasting',complete,undefined,undefined,options);
 assert.deepEqual(calls,[['summary',['a']],['select',['a','b','c']],['detail',['a']]]);
 calls.length=0;
 await fastFilter(snapshot,'forecasting',complete,undefined,undefined,{...options,model:'another-model'});
 assert.equal(calls[0][0],'summary');assert.equal(calls.length,3);
});
test('thorough bypasses selection and checks quick exclusions; cached negatives are never treated as full checks',async()=>{
 const {cache,calls,complete}=setup(),options={cache};
 await fastFilter(snapshot,'forecasting',complete,undefined,undefined,options);calls.length=0;
 const thorough=await fastFilter(snapshot,'forecasting',complete,undefined,undefined,{...options,thorough:true});
 assert.deepEqual(calls,[['detail',['c']]]);assert.equal(thorough.mode,'thorough');assert.ok(thorough.matches.c);
 calls.length=0;await fastFilter(snapshot,'forecasting',complete,undefined,undefined,{...options,thorough:true});assert.equal(calls.length,0);
});
test('invalid summaries or candidate lists fail without publishing a result',async()=>{
 for(const invalid of [{summaries:[]},{summaries:[{id:'a',summary:'x'},{id:'a',summary:'x'},{id:'c',summary:'x'}]}]) {
  await assert.rejects(()=>fastFilter(snapshot,'x',async()=>response(invalid)),/summar/i);
 }
 for(const candidates of [['unknown'],['a','a'],null]) {
  const {complete}=setup();
  await assert.rejects(()=>fastFilter(snapshot,'x',async context=>context.systemPrompt.startsWith('Select')?response({candidates}):complete(context)),/selection/i);
 }
});
test('cancel at every model stage ignores late completion and publishes no full-result cache',async()=>{
 for(const stage of ['Summarise','Select','You assess']) {
  const {cache,complete}=setup(),controller=new AbortController();let fullWrites=0;
  const guarded={get:cache.get,set:async(k,v)=>{if(k[2]==='result')fullWrites++;await cache.set(k,v);}};
  await assert.rejects(()=>fastFilter(snapshot,'x',async context=>{
   const result=await complete(context);if(context.systemPrompt.startsWith(stage))controller.abort();return result;
  },controller.signal,undefined,{cache:guarded}),/cancelled/);
  assert.equal(fullWrites,0);
 }
});
test('failed assessment or cache write cannot publish a complete result',async()=>{
 const {cache,complete}=setup();
 await assert.rejects(()=>fastFilter(snapshot,'x',async context=>{
  if(context.systemPrompt.startsWith('You assess'))throw new Error('network failed');return complete(context);
 },undefined,undefined,{cache}),/network/);
 await assert.rejects(()=>fastFilter(snapshot,'x',complete,undefined,undefined,{cache:{get:async()=>null,set:async()=>{throw new Error('disk full');}}}),/disk full/);
});
test('disk cache writes are atomic under concurrent writers and malformed entries are misses',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'career-cache-test-'));
 try {
  const cache=diskCache(dir);
  await Promise.all(Array.from({length:12},(_,i)=>cache.set('key',{i,text:'x'.repeat(1000)})));
  assert.equal(typeof (await cache.get('key')).i,'number');
  const files=await readdir(dir);assert.equal(files.length,1);
  await writeFile(join(dir,files[0]),'{broken');assert.equal(await cache.get('key'),null);
 } finally {await rm(dir,{recursive:true,force:true});}
});

test('multiline prompts and restored normalized prompts share cached results',async()=>{
 const {cache,calls,complete}=setup();
 const saved=await fastFilter(snapshot,'forecasting\n  include adjacent roles',complete,undefined,undefined,{cache});
 calls.length=0;
 await fastFilter(snapshot,'forecasting\n  include adjacent roles',complete,undefined,undefined,{cache});
 await fastFilter(snapshot,saved.prompt,complete,undefined,undefined,{cache});
 assert.equal(calls.length,0);
});
test('overlong summary is corrected once with a specific reason and cached only after validation',async()=>{
 const {cache,complete,calls}=setup();let attempts=0;
 const result=await fastFilter(snapshot,'x',async context=>{
  if(context.systemPrompt.startsWith('Summarise')) {
   attempts++;
   if(attempts===1)return response({summaries:jobs.map(j=>({id:j.id,summary:'x'.repeat(901)}))});
   assert.match(JSON.parse(context.messages[0].content[0].text).correction,/901 characters; maximum is 900/);
  }
  return complete(context);
 },undefined,undefined,{cache});
 assert.equal(attempts,2);assert.ok(result.matches.a);
 calls.length=0;await fastFilter(snapshot,'x',complete,undefined,undefined,{cache});assert.equal(calls.length,0);
});
test('summary retry is bounded and reports exact failure without retrying transport errors',async()=>{
 let calls=0;
 await assert.rejects(()=>fastFilter(snapshot,'x',async()=>{
  calls++;return response({summaries:jobs.map(j=>({id:j.id,summary:'x'.repeat(950)}))});
 }),/after one retry: Summary for role a was 950 characters/);
 assert.equal(calls,2);calls=0;
 await assert.rejects(()=>fastFilter(snapshot,'x',async()=>{calls++;throw new Error('network failed');}),/network failed/);
 assert.equal(calls,1);
});
test('cancelling during summary repair does not cache or publish the repaired response',async()=>{
 const controller=new AbortController();let calls=0,writes=0;
 await assert.rejects(()=>fastFilter(snapshot,'x',async()=>{
  calls++;
  if(calls===1)return response({summaries:[]});
  controller.abort();return response({summaries:jobs.map(j=>({id:j.id,summary:'Valid evidence.'}))});
 },controller.signal,undefined,{cache:{get:async()=>null,set:async()=>writes++}}),/cancelled/);
 assert.equal(calls,2);assert.equal(writes,0);
});
