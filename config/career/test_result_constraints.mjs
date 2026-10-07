import test from 'node:test';
import assert from 'node:assert/strict';
import {curate,companyKey,parseConstraints,constraintNotice,validResultConstraints} from './result-constraints.mjs';
import {fastFilter} from './fast-filter.mjs';
import {restoreFilter} from './prompt-filter.mjs';
const constraints={min:5,max:8,uniqueCompanies:true,random:true};
const jobs=Array.from({length:30},(_,i)=>({id:String(i),company:i<20?' Wayve ':i===20?'wayve':i===21?'':`Company ${i}`,summary:'Evidence',matches:[],evidence_hash:'v1'}));
const matches=Object.fromEntries(jobs.map(j=>[j.id,{level:'uncertain',reason:'Limited evidence.'}]));
const response=data=>({stopReason:'stop',content:[{type:'text',text:JSON.stringify(data)}]});
test('count and company constraints hold after sampling, unknowns excluded, evidence unchanged',()=>{
 const result=curate(matches,jobs,constraints,()=>0);
 assert.equal(Object.keys(result).length,8);
 const keys=jobs.filter(j=>Object.hasOwn(result,j.id)).map(j=>companyKey(j.company));
 assert.equal(new Set(keys).size,8);assert.ok(!keys.includes(''));
 for(const id of Object.keys(result))assert.deepEqual(result[id],matches[id]);
 assert.equal(companyKey(' Foo  BAR '),'foo bar');assert.equal(companyKey('Unknown'),'');
});
test('company groups are sampled before roles, without weighting prolific employers',()=>{
 const bounds=[];curate(matches,jobs,{...constraints,max:1},n=>{bounds.push(n);return 0;});
 // Nine company groups, not 29 individual postings, in the initial shuffle.
 assert.deepEqual(bounds.slice(0,8),[9,8,7,6,5,4,3,2]);
});
test('insufficient and zero matches remain honest; broad results remain unbounded',()=>{
 for(const pool of [{}, {'0':matches['0'],'1':matches['1'],'21':matches['21']}]) {
  const result=curate(pool,jobs,constraints,()=>0);
  assert.ok(Object.keys(result).length<=1);
  assert.match(constraintNotice({matches:result,constraints}),/requested at least 5/);
 }
 assert.deepEqual(curate(matches,jobs,{min:null,max:null,uniqueCompanies:false,random:false}),matches);
});
test('invalid fresh/restored constraint metadata rejected',()=>{
 for(const c of [{},null,{...constraints,min:9},{...constraints,max:1.5},{...constraints,random:'yes'}])assert.throws(()=>parseConstraints(JSON.stringify(c)));
 const base={active:true,prompt:'x',assessed:Object.fromEntries(jobs.map(j=>[j.id,''])),matches,constraints};
 assert.equal(restoreFilter(base),null);
 assert.equal(validResultConstraints({...base,matches:{'0':matches['0'],'1':matches['1']}},jobs),false);
});
test('quick/thorough apply constraints after thin and cached detail; reapply stable; malformed parsing retries',async()=>{
 const store=new Map(),cache={get:async k=>store.get(JSON.stringify(k)),set:async(k,v)=>store.set(JSON.stringify(k),v)};
 let calls=0,parseCalls=0;
 const complete=async ctx=>{
  calls++;const body=JSON.parse(ctx.messages[0].content[0].text);
  if(ctx.systemPrompt.startsWith('Parse only')) {parseCalls++;return response(parseCalls===1?{...constraints,min:9}:constraints);}
  if(ctx.systemPrompt.startsWith('Select'))return response({candidates:jobs.slice(0,27).map(j=>j.id)});
  return response({results:body.jobs.map(j=>({id:j.id,...matches[j.id]}))});
 };
 const snapshot={jobs:jobs.map(j=>({...j,summary:''}))};
 const first=await fastFilter(snapshot,'exact prompt',complete,undefined,undefined,{cache});
 assert.equal(Object.keys(first.matches).length,8);assert.ok(validResultConstraints(first,jobs));
 const previous=calls;
 assert.deepEqual(await fastFilter(snapshot,'exact prompt',complete,undefined,undefined,{cache}),first);assert.equal(calls,previous);
 const thorough=await fastFilter(snapshot,'exact prompt',complete,undefined,undefined,{cache,thorough:true});
 assert.ok(validResultConstraints(thorough,jobs));assert.equal(calls,previous+1); // all details reused
});
test('constraint parsing cancellation never publishes a result',async()=>{
 const controller=new AbortController();let writes=0;
 await assert.rejects(()=>fastFilter({jobs},'x',async()=>{controller.abort();return response(constraints);},controller.signal,undefined,{cache:{get:async()=>null,set:async()=>writes++}}),/cancelled/);
 assert.equal(writes,0);
});
test('bounded random reserve caps description work; ordinary search still checks all candidates',async()=>{
 const inventory=Array.from({length:100},(_,i)=>({id:String(i),company:`Company ${i}`,summary:'Existing fit evidence'}));
 for(const bounded of [true,false]) {
  let assessed=0;
  const result=await fastFilter({jobs:inventory},'prompt',async ctx=>{
   const body=JSON.parse(ctx.messages[0].content[0].text);
   if(ctx.systemPrompt.startsWith('Parse only'))return response(bounded?constraints:{min:null,max:null,uniqueCompanies:false,random:false});
   if(ctx.systemPrompt.startsWith('Select'))return response({candidates:inventory.map(j=>j.id)});
   assessed+=body.jobs.length;
   return response({results:body.jobs.map(j=>({id:j.id,level:'related',reason:'Existing fit evidence.'}))});
  });
  assert.equal(assessed,bounded?24:100);assert.equal(Object.keys(result.matches).length,bounded?8:100);
 }
});
test('malformed current result cache is ignored; stale cache namespace never reused',async()=>{
 const corrupt={active:true,prompt:'x',matches:{'0':matches['0'],'1':matches['1']},assessed:Object.fromEntries(jobs.map(j=>[j.id,'v1'])),constraints};
 let calls=0;
 const result=await fastFilter({jobs},'x',async ctx=>{
  calls++;const body=JSON.parse(ctx.messages[0].content[0].text);
  if(ctx.systemPrompt.startsWith('Parse only'))return response(constraints);
  if(ctx.systemPrompt.startsWith('Select'))return response({candidates:jobs.map(j=>j.id)});
  return response({results:body.jobs.map(j=>({id:j.id,...matches[j.id]}))});
 },undefined,undefined,{cache:{get:async key=>{assert.equal(key[0],'career-filter-v4');return key[2]==='result'?corrupt:null;},set:async()=>{}}});
 assert.ok(calls>0);assert.ok(validResultConstraints(result,jobs));
});
