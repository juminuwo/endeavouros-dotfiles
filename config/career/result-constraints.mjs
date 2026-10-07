import {randomInt} from 'node:crypto';
import {FilterOutputError,parseJSON} from './filter-response.mjs';

export const constraintSystem=`Parse only result-set instructions in the user's job search prompt. Return ONLY JSON {"min":null,"max":null,"uniqueCompanies":false,"random":false}. min/max are positive integer result counts, or null when unspecified. An exact count sets both; a range sets both endpoints; at most sets max only; at least sets min only. Counts refer to requested roles, never years of experience, salary or other job requirements. Different/distinct companies means uniqueCompanies true. Random selection/sampling means random true. Do not invent constraints for ordinary broad searches. Do not assess jobs.`;
export function validConstraints(c) {
  return !!c && typeof c==='object' && !Array.isArray(c) &&
    ['min','max'].every(k=>c[k]===null || (Number.isSafeInteger(c[k]) && c[k]>0)) &&
    (c.min===null || c.max===null || c.min<=c.max) &&
    typeof c.uniqueCompanies==='boolean' && typeof c.random==='boolean';
}
export function parseConstraints(text) {
  const c=parseJSON(text);
  if(!validConstraints(c))throw new FilterOutputError('Result constraints require positive integer or null min/max, ordered bounds, and boolean uniqueCompanies/random.');
  return {min:c.min,max:c.max,uniqueCompanies:c.uniqueCompanies,random:c.random};
}
export function companyKey(company) {
  if(typeof company!=='string')return '';
  const key=company.trim().replace(/\s+/g,' ').toLowerCase();
  return ['unknown','unknown company','n/a','na','not specified','unspecified','-'].includes(key)?'':key;
}
function shuffle(rows,draw) {
  const copy=[...rows];
  for(let i=copy.length-1;i>0;i--) {const j=draw(i+1);[copy[i],copy[j]]=[copy[j],copy[i]];}
  return copy;
}
export function curate(matches,jobs,constraints,draw=randomInt) {
  let ids=jobs.filter(j=>Object.hasOwn(matches,j.id)).map(j=>j.id);
  if(constraints.uniqueCompanies) {
    const groups=new Map();
    for(const job of jobs) {
      const key=companyKey(job.company);
      if(!key || !Object.hasOwn(matches,job.id))continue;
      if(!groups.has(key))groups.set(key,[]);
      groups.get(key).push(job.id);
    }
    const pool=[...groups.values()];
    ids=(constraints.random?shuffle(pool,draw):pool).map(group=>group[constraints.random?draw(group.length):0]);
  } else if(constraints.random)ids=shuffle(ids,draw);
  ids=ids.slice(0,constraints.max??ids.length);
  return Object.fromEntries(ids.map(id=>[id,matches[id]]));
}
export function constraintNotice(filter) {
  const min=filter.constraints?.min,count=Object.keys(filter.matches).length;
  return min!==null && min!==undefined && count<min
    ? `${count} matching ${filter.constraints.uniqueCompanies?'known companies':'roles'} found among checked candidates; requested at least ${min}.${filter.mode==='thorough'?'':' Try Search thoroughly.'}` : '';
}
export function validResultConstraints(filter,jobs) {
  if(!validConstraints(filter.constraints))return false;
  const ids=Object.keys(filter.matches),c=filter.constraints;
  if(c.max!==null && ids.length>c.max)return false;
  if(!jobs)return true;
  const byId=new Map(jobs.map(j=>[j.id,j]));
  if(ids.some(id=>!byId.has(id)))return false;
  if(c.uniqueCompanies) {
    const keys=ids.map(id=>companyKey(byId.get(id).company));
    if(keys.some(key=>!key) || new Set(keys).size!==keys.length)return false;
  }
  return true;
}
