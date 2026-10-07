// Pure UI policy: these operations never call a model or write the inventory.
export const tabs = ['Discover', 'Shortlist', 'Applications', 'Dismissed'];
export const clean = value => String(value ?? '').replace(/[\u0000-\u001f\u007f-\u009f]/g, ' ').replace(/\s+/g, ' ').trim();
export function family(job) {
  const t = job.title.toLowerCase();
  if (/data scien/.test(t) && /senior|lead|principal|staff/.test(t)) return 0;
  if (/data scien/.test(t)) return 1;
  if (/applied scien|machine learning scien/.test(t)) return 2;
  return 3;
}
export function filtered(jobs, tab, query = '', lane = 'All roles') {
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return jobs.filter(j => {
    if (tab === 'Discover' && (j.lifecycle !== 'active' || ['dismissed', 'applied', 'draft', 'shortlisted'].includes(j.status))) return false;
    if (tab === 'Shortlist' && j.status !== 'shortlisted') return false;
    if (tab === 'Applications' && !['draft', 'applied'].includes(j.status)) return false;
    if (tab === 'Dismissed' && j.status !== 'dismissed') return false;
    if (lane === 'Data science' && family(j) > 1) return false;
    if (lane === 'ML / applied science' && family(j) < 2) return false;
    const haystack = `${j.title} ${j.company} ${j.location}`.toLowerCase();
    return words.every(w => haystack.includes(w));
  }).sort((a, b) => family(a) - family(b) || (b.score ?? 0) - (a.score ?? 0) || a.company.localeCompare(b.company) || a.id.localeCompare(b.id));
}
export function capability(job, action) {
  if (!job) return 'Select a role first.';
  if (['shortlisted', 'dismissed', 'unseen'].includes(action) && job.status === 'applied') return 'Already applied. Its application history is retained.';
  if (['shortlisted', 'draft', 'applied'].includes(action) && job.lifecycle !== 'active') return 'This listing is no longer active. Open it to check before proceeding.';
  if (action === 'applied' && job.status === 'dismissed') return 'Restore this role before marking it applied.';
  return null;
}
export function safeUrl(value) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; }
  catch { return null; }
}

// A committed mutation must remain distinguishable from a failed projection/read.
export async function saveAndReload(save, load) {
  const saved = await save();
  try { return {saved, data: await load()}; }
  catch (error) { return {saved, refreshError: clean(error.message)}; }
}
export async function repairAndReload(repair, load) {
  let warning;
  try { const result = await repair(); warning = result.warning; }
  catch (error) { warning = clean(error.message); }
  return {data: await load(), warning};
}
