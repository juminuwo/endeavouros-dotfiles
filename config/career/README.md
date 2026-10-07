# Career workspace for Pi

Run `career` from any directory. Requires Pi 1.0.4-compatible extension APIs, Python 3, and an existing Pi model login (`pi` then `/login`). Career defaults to OpenAI GPT-6 Luna (`gpt-6-luna`); no credentials are copied.

The launcher opens the private Obsidian Career folder and loads this extension. No model call occurs just to browse. The vault's existing job-market collector supplies vacancies. The extension supplies normal terminal navigation, discussions with the selected role/profile loaded, shortlisting and versioned application drafts.

## Keys

- Arrows / j,k: select; Tab or 1–4: Discover, Shortlist, Applications, Dismissed.
- Enter: action menu; /: text filter; f: role-family filter; v: expanded detail.
- g: agent prompt filter — describe roles, edit the prompt, reapply, search thoroughly or clear it.
- a: discuss; s: shortlist; d: dismiss; u: restore; p: prepare draft.
- o: open listing or draft; m: confirm already applied; r: reload saved data.
- ?: help; Esc/q: chat; Ctrl+Alt+C or `/career`: return to the board.

The first ordering favours Senior DS titles, then other DS, applied science and MLE. Scores within those groups are historical tracker scores, not fresh fit judgments. The agent checks requirements when discussing/preparing; it cannot infer live vacancy status solely from an HTTP 200 response.

Press **s** to save a role, then **2** to find it in Shortlist, including after restarting. Preparing a draft moves it to **3 — Applications**. Filters apply to every destination: clear **g**, **/** and **f** filters if a saved role seems missing.

## Agent prompt filter

Press **g** and describe what you want, e.g. “Look for forecasting roles, including tangential work in demand, capacity and inventory planning.” Quick search selects possible matches from compact summaries of all active and saved roles in one model request, then checks only the candidates against cached descriptions/excerpts. Summaries are generated once and regenerated when the underlying evidence changes. The first run has a summary preparation stage; later prompt changes reuse that work. It does not require a literal title match, collect new vacancies or verify live listings. Roles with insufficient evidence may appear as **uncertain** rather than invented matches. Each included role displays a direct/related/tangential/uncertain label and reason. Direct matches sort first.

The filter intersects the current destination, text filter and role family. **g** works even with no visible matches. **Clear** disables the agent filter and retains its prompt; it does not clear the other filters or change shortlist/application decisions. **Edit** prefills the last successful prompt. **Reapply** runs that prompt against a fresh snapshot. New/changed roles are flagged for reapplication; unassessed new roles are not silently treated as nonmatches. A failed/cancelled run keeps the previous result intact. Escape cancels while matching. Malformed summary responses get one corrective retry with a specific validation reason. Completed summary batches remain cached if a later batch fails, so retrying reuses that work.

**Search thoroughly** skips summary selection and checks every eligible role against the fuller cached evidence. It can find details omitted from summaries; it still does not verify live vacancies. Valid full-description assessments can be reused in either mode, but quick-search exclusions never count as thorough checks. Repeating the same prompt and inventory restores cached results without model calls. Cache keys include model, mode, prompt and actual evidence; a changed or expired description invalidates relevant work.

Filter state is saved with the Pi session. `career --continue` restores it; a fresh `career` session starts unfiltered. Matching uses the selected Career model; ordinary browsing remains local. Results publish only when every batch is complete and validated.

## Storage and boundaries

Default root: `~/Documents/online-personal/Personal/Career`. Set `CAREER_ROOT` for an isolated fixture or another vault. Inventory is read-only: `Job Market/data/job-listings.json`. Reusable filter artifacts live in `data/agent-filter-cache/`, separate from decisions, with atomic content-addressed writes. Interactive decisions live in `data/career-workspace.json`; the generated `Career Board.md` is a readable projection. Existing tracker user states are inherited until the first explicit interactive decision. TUI choices are not synced back into the old tracker; this avoids racing its whole-file saves. The manual Application Pipeline remains untouched.

Versioned packs live at `Applications/<job-id>/Application-vNNN.md`. Preparing does not mean submitted. A mark-applied action records user confirmation only; no application or message is sent. Profile context is taken from existing CV, references, strategy and search-state notes; practice never blocks search.

The backend serializes writes with a stable sidecar flock and checks observed per-role revisions. A failed board projection leaves the JSON decision intact and can be repaired with r. A failed state commit after a pack write reports its retained path; a later draft never overwrites that orphan. Backend operations have a bounded UI timeout; after a timeout reload before repeating an action.

## Development

- `node --test config/career/test_*.mjs`
- `python -m unittest discover -s config/career -p 'test_backend.py'`
- `CAREER_ROOT=/path/to/copied-fixture config/bin/career --offline`

Use fixture vaults for stateful UI tests. Real inventory may be used for read-only smoke checks. Extension modules use packages provided by the installed Pi runtime; no project npm install is necessary. The launcher is linked by dotbot. Pi is a portable AUR dependency in the repository package list.

Extend the role action menu and backend commands together. Keep navigation/status changes deterministic; use the model for interpretation and prose. Read the root DESIGN.md and preserve the stored-state guards when adding actions.
