# Career workspace for Pi

Run `career` from any directory. Requires Pi 1.0.4-compatible extension APIs, Python 3, and an existing Pi model login (`pi` then `/login`). It uses the model configured in Pi; no credentials are copied.

The launcher opens the private Obsidian Career folder and loads this extension. No model call occurs just to browse. The vault's existing job-market collector supplies vacancies. The extension supplies normal terminal navigation, discussions with the selected role/profile loaded, shortlisting and versioned application drafts.

## Keys

- Arrows / j,k: select; Tab or 1–4: Discover, Shortlist, Applications, Dismissed.
- Enter: action menu; /: filter; f: role-family filter; v: expanded detail.
- a: discuss; s: shortlist; d: dismiss; u: restore; p: prepare draft.
- o: open listing or draft; m: confirm already applied; r: reload saved data.
- ?: help; Esc/q: chat; Ctrl+Alt+C or `/career`: return to the board.

The first ordering favours Senior DS titles, then other DS, applied science and MLE. Scores within those groups are historical tracker scores, not fresh fit judgments. The agent checks requirements when discussing/preparing; it cannot infer live vacancy status solely from an HTTP 200 response.

## Storage and boundaries

Default root: `~/Documents/online-personal/Personal/Career`. Set `CAREER_ROOT` for an isolated fixture or another vault. Inventory is read-only: `Job Market/data/job-listings.json`. Interactive decisions live in `data/career-workspace.json`; the generated `Career Board.md` is a readable projection. Existing tracker user states are inherited until the first explicit interactive decision. TUI choices are not synced back into the old tracker; this avoids racing its whole-file saves. The manual Application Pipeline remains untouched.

Versioned packs live at `Applications/<job-id>/Application-vNNN.md`. Preparing does not mean submitted. A mark-applied action records user confirmation only; no application or message is sent. Profile context is taken from existing CV, references, strategy and search-state notes; practice never blocks search.

The backend serializes writes with a stable sidecar flock and checks observed per-role revisions. A failed board projection leaves the JSON decision intact and can be repaired with r. A failed state commit after a pack write reports its retained path; a later draft never overwrites that orphan. Backend operations have a bounded UI timeout; after a timeout reload before repeating an action.

## Development

- `node --test config/career/test_model.mjs`
- `python -m unittest discover -s config/career -p 'test_backend.py'`
- `CAREER_ROOT=/path/to/copied-fixture config/bin/career --offline`

Use fixture vaults for stateful UI tests. Real inventory may be used for read-only smoke checks. Extension modules use packages provided by the installed Pi runtime; no project npm install is necessary. The launcher is linked by dotbot. Pi is a portable AUR dependency in the repository package list.

Extend the role action menu and backend commands together. Keep navigation/status changes deterministic; use the model for interpretation and prose. Read the root DESIGN.md and preserve the stored-state guards when adding actions.
