import { Input, matchesKey, truncateToWidth, visibleWidth, wrapTextWithAnsi } from '@earendil-works/pi-tui';
import { tabs, filtered, clean, capability } from './model.mjs';
import { unassessedCount } from './prompt-filter.mjs';

export class CareerScreen {
  focused = true;
  filter = new Input();
  filtering = false;
  help = false;
  detail = false;
  scroll = 0;
  rows = 12;
  jobs: any[] = [];
  updated = '';
  notice = 'Loading your vacancies…';
  busy = true;
  error = false;
  disposed = false;
  constructor(public tui: any, public theme: any, public state: any, public done: any, public action: any) {
    this.filter.setValue(state.query);
  }
  invalidate() { this.filter.invalidate?.(); }
  dispose() { this.disposed = true; }
  redraw() { if (!this.disposed) this.tui.requestRender(); }
  setData(data: any) {
    this.jobs = data.jobs.map((job:any)=>({...job,title:clean(job.title)||'Untitled role',company:clean(job.company)||'Unknown company',location:clean(job.location)}));
    this.updated = clean(data.inventory_updated_at ?? data.updated_at);
    this.busy = false;
    this.error = false;
    this.notice = data.warning || (this.state.semantic?.active ? 'Prompt matches first. g changes or clears the agent filter.' : 'Senior DS first. Browse with ↓ / ↑, then Enter for actions.');
    this.normalise(); this.redraw();
  }
  items() { return filtered(this.jobs, tabs[this.state.tab], this.state.query, this.state.lane, this.state.semantic); }
  normalise() {
    const list = this.items();
    const found = list.findIndex(j => j.id === this.state.id);
    this.state.index = found >= 0 ? found : Math.max(0, Math.min(this.state.index, list.length - 1));
    this.state.id = list[this.state.index]?.id;
  }
  selected() { return this.items()[this.state.index]; }
  async run(name: string) {
    if (this.busy) return;
    const job = this.selected();
    const denied = ({shortlist:'shortlisted', dismiss:'dismissed', restore:'unseen', prepare:'draft', applied:'applied'} as any)[name];
    const reason = denied && capability(job, denied);
    if (reason) { this.notice = reason; this.error = true; this.redraw(); return; }
    this.busy = true; this.notice = 'Working…'; this.error = false; this.redraw();
    try { await this.action(name, job, this); }
    catch (e: any) { this.notice = clean(e.message); this.error = true; }
    finally { this.busy = false; this.redraw(); }
  }
  handleInput(data: string) {
    if (this.filtering) {
      if (matchesKey(data, 'escape') || matchesKey(data, 'return')) {
        this.filtering = false; this.filter.focused = false;
      } else this.filter.handleInput(data);
      this.state.query = this.filter.getValue(); this.state.index = 0; this.state.id = undefined;
      this.normalise(); this.redraw(); return;
    }
    if (matchesKey(data, 'ctrl+c')) { this.done({kind:'close'}); return; }
    if (this.help) { this.help = false; this.redraw(); return; }
    if (matchesKey(data, 'escape')) {
      if (this.detail) { this.detail = false; this.scroll = 0; this.redraw(); }
      else this.done({kind:'close'});
      return;
    }
    if (data === '?') { this.help = true; this.redraw(); return; }
    if (this.busy) return;
    if (data === 'g') { void this.run('agent-filter'); return; }
    if (data === '/') { this.filtering = true; this.filter.focused = true; this.redraw(); return; }
    if (data === 'q') { this.done({kind:'close'}); return; }
    if (data === 'v') { this.detail = !this.detail; this.scroll = 0; this.redraw(); return; }
    if (matchesKey(data, 'tab') || matchesKey(data, 'right') || matchesKey(data, 'left') || ['1','2','3','4'].includes(data)) {
      const delta = matchesKey(data, 'left') ? -1 : 1;
      this.state.tab = ['1','2','3','4'].includes(data) ? Number(data)-1 : (this.state.tab + delta + tabs.length) % tabs.length;
      this.state.index = 0; this.state.id = undefined; this.scroll = 0; this.detail = false;
      this.normalise(); this.redraw(); return;
    }
    if (data === 'f') {
      const lanes = ['All roles', 'Data science', 'ML / applied science'];
      this.state.lane = lanes[(lanes.indexOf(this.state.lane) + 1) % lanes.length];
      this.state.index = 0; this.state.id = undefined; this.normalise(); this.redraw(); return;
    }
    if (matchesKey(data, 'down') || data === 'j' || matchesKey(data, 'up') || data === 'k' || matchesKey(data, 'pageDown') || matchesKey(data, 'pageUp')) {
      const direction = (matchesKey(data, 'up') || data === 'k' || matchesKey(data, 'pageUp')) ? -1 : 1;
      const jump = (matchesKey(data, 'pageDown') || matchesKey(data, 'pageUp')) ? this.rows : 1;
      if (this.detail) this.scroll = Math.max(0, this.scroll + direction * jump);
      else {
        this.state.index = Math.max(0, Math.min(this.items().length - 1, this.state.index + direction * jump));
        this.state.id = this.selected()?.id;
      }
      this.redraw(); return;
    }
    const keys:any = {s:'shortlist', d:'dismiss', u:'restore', a:'ask', p:'prepare', o:'open', r:'refresh', m:'applied'};
    if (matchesKey(data,'return')) void this.run('menu');
    else if (keys[data]) void this.run(keys[data]);
  }
  detailLines(job: any, width: number) {
    const th = this.theme;
    if (!job) return ['No role selected.', '', 'Try g to change/clear the agent filter, or / for text.'];
    const lines:string[] = [];
    const add = (s: string, color='text') => { lines.push(...wrapTextWithAnsi(th.fg(color, clean(s)), Math.max(8,width))); };
    add(job.title, 'accent'); add(job.company); lines.push('');
    add(`${job.location || 'Location unknown'}${job.workplace ? ' · '+job.workplace : ''}`, 'muted');
    add(`Salary: ${typeof job.salary === 'object' && job.salary ? JSON.stringify(job.salary) : job.salary || 'not published'}`, 'muted');
    add(`Your status: ${job.status}   Listing: ${job.lifecycle}`, job.lifecycle === 'active' ? 'success' : 'warning');
    add(`Last seen: ${job.last_seen?.slice(0,10) || 'unknown'} — verify before applying`, 'muted');
    const match=this.state.semantic?.active && this.state.semantic.matches[job.id];
    if (match) { lines.push('');add(`Prompt match: ${match.level}${this.state.semantic.assessed[job.id] !== (job.evidence_hash || '') ? ' (older evidence; reapply)' : ''}`, match.level==='uncertain'?'warning':'accent');add(match.reason); }
    lines.push(''); add('Why it may fit', 'accent');
    for (const m of (job.matches?.length ? job.matches : ['No detailed fit assessment yet. Ask the agent.'])) add('• '+m);
    lines.push(''); add('What to check', 'warning');
    for (const g of [...(job.gaps || []), ...(job.uncertainties || [])]) add('• '+g);
    if (!job.gaps?.length && !job.uncertainties?.length) add('Requirements need checking against the full listing.');
    lines.push(''); if (job.summary) add(job.summary);
    lines.push(''); add(`Legacy ML score: ${job.score ?? 'unscored'}${job.priority ? ' / '+job.priority : ''}. Not a Senior DS ranking.`, 'dim');
    if (job.pack_path) { lines.push(''); add('Draft saved: '+job.pack_path, 'success'); }
    lines.push(''); add(job.url || 'No listing link available', 'dim');
    return lines;
  }
  render(width: number): string[] {
    const th = this.theme;
    const w = Math.max(1,width);
    const height = Math.max(12, Math.min(45, (this.tui.terminal?.rows || process.stdout.rows || 32) - 5));
    const out:string[] = [];
    const line = (s='') => out.push(truncateToWidth(s,w));
    line(th.fg('accent', th.bold(' Career ')) + th.fg('muted', 'Your next role, one good decision at a time'));
    line(tabs.map((t,i) => i === this.state.tab ? th.fg('accent',th.bold(` ${i+1} ${t} `)) : th.fg('muted',` ${i+1} ${t} `)).join('  '));
    line(th.fg('borderMuted','─'.repeat(w)));
    if (this.filtering) {
      for (const l of this.filter.render(Math.max(1,w-10))) line(' Filter: '+l);
    } else line(th.fg('muted',` / Filter: ${this.state.query || 'all companies and locations'}    f: ${this.state.lane}`));
    const semantic=this.state.semantic;
    const pending=unassessedCount(this.jobs,semantic);
    const label=semantic?.active ? `${pending ? `${pending} new/changed — reapply · ` : ''}${semantic.prompt}` : semantic?.prompt ? `off (last: ${semantic.prompt})` : 'off';
    line(th.fg(semantic?.active?'accent':'muted',` g Agent filter: ${label}`));
    line(th.fg('dim', ` Vault profile loaded on discussion · Inventory ${this.updated?.slice(0,16).replace('T',' ') || 'not loaded'}`));
    if (this.help) {
      for (const s of [
        ' Find work without remembering prompts or file names.', '',
        ' ↑/↓ or j/k  Browse roles        1–4 / Tab  Change section',
        ' /  Search title/company/place  f  Cycle role family',
        ' g  Agent filter: describe, edit, reapply or clear',
        ' Includes direct, related, tangential and uncertain matches.',
        ' Enter  Show all actions        v  Expand details (↑/↓ scroll)',
        ' a  Discuss fit / ask anything  p  Prepare application draft',
        ' s  Shortlist                   d  Dismiss     u  Restore',
        ' o  Open listing or draft       m  Mark applied (confirmation)',
        ' r  Reload saved vacancies      Esc / q  Return to agent chat', '',
        ' In chat: Ctrl+Alt+C returns here. /career also works.',
        ' Your choices are saved to the vault immediately.',
        ' Agent filtering, asking and preparing use your Pi model.',
        ' Preparation creates a draft. You review and submit it.', '',
        ' Press any key to return.'
      ]) line(th.fg('text', s));
      return [...out.slice(0, Math.max(1,height-1)), truncateToWidth(th.fg('muted',' Any key returns to roles. Resize for more help.'),w)];
    }
    const bodyHeight = Math.max(4,height-out.length-5);
    this.rows = bodyHeight;
    const list = this.items();
    const selected = this.selected();
    const split = w >= 105 && !this.detail;
    const leftWidth = split ? Math.floor(w * 0.46) : w;
    const rightWidth = split ? w - leftWidth - 4 : w;
    const details = this.detailLines(selected, rightWidth);
    this.scroll = Math.min(this.scroll, Math.max(0,details.length-bodyHeight));
    const start = Math.max(0,Math.min(this.state.index - Math.floor(bodyHeight/2),list.length-bodyHeight));
    for (let row=0; row<bodyHeight; row++) {
      if (this.detail) { line(' '+(details[this.scroll+row] || '')); continue; }
      const j = list[start+row];
      let left='';
      if (j) {
        const chosen = j.id === selected?.id;
        const label = `${chosen ? '›' : ' '} ${j.company}  ${j.title}`;
        left = th.fg(chosen ? 'accent' : 'text',chosen ? th.bold(label) : label);
        if (chosen) left = th.bg('selectedBg',left);
      } else if (!list.length && row===1) left = th.fg('muted', ' No roles here. g: agent filter · /: text filter · Tab: section.');
      if (split) {
        left = truncateToWidth(left,leftWidth);
        left += ' '.repeat(Math.max(0,leftWidth-visibleWidth(left)));
        line(left+th.fg('borderMuted',' │ ')+(details[row] || ''));
      } else line(left);
    }
    line(th.fg('borderMuted','─'.repeat(w)));
    line(th.fg(this.error ? 'error' : this.busy ? 'warning' : 'success',' '+this.notice));
    line(th.fg('muted',` ${list.length ? this.state.index+1 : 0}/${list.length} roles   Enter Actions   a Ask   s Shortlist   p Prepare   v Details`));
    line(th.fg('dim',' g Agent filter   / Text   f Role family   ? Help   Esc Chat   Ctrl+Alt+C Reopen'));
    return out;
  }
}


export class FilterProgress {
  count=0; total=0; cost=0;
  constructor(public tui:any,public theme:any,public prompt:string,public cancel:()=>void) {}
  invalidate() {}
  dispose() {this.cancel();}
  update(progress:any) {Object.assign(this,progress);this.tui.requestRender();}
  handleInput(data:string) {
    if(matchesKey(data,'escape') || matchesKey(data,'ctrl+c')) this.cancel();
  }
  render(width:number) {
    const lines=[this.theme.fg('accent',this.theme.bold(' Agent filter')), '',
      ...wrapTextWithAnsi(clean(this.prompt),Math.max(8,width)), '',
      `${this.count} / ${this.total || '…'} roles assessed. Includes tangential and uncertain matches.`,
      'Matching cached listing evidence, not checking live vacancies.',
      'Previous results stay in place until this run completes.',
      this.cost ? `Estimated model cost so far: $${this.cost.toFixed(3)}` : '',
      '',this.theme.fg('muted','Escape cancels and keeps your previous filter.')];
    return lines.map(line=>truncateToWidth(line,width));
  }
}
