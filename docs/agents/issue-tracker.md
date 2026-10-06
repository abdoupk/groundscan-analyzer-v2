# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone.

> **Repo:** issues live in **`abdoupk/groundscan-analyzer-v2`** (private), wired up as `origin`. `gh`
> infers this automatically from the remote, so run commands from inside the clone. The `gh` CLI is
> authenticated as `abdoupk`.
>
> Note the name: an older, separate repo exists at `abdoupk/groundscan-analyzer`. This working tree is
> **v2**, and its issues go to `groundscan-analyzer-v2`. Pass `-R abdoupk/groundscan-analyzer-v2`
> explicitly if you ever run `gh` from outside the clone.

## Reading `gh` output: encoding

**Verified 2026-10-05. PowerShell captures `gh`'s stdout through `[Console]::OutputEncoding`, which on this machine is `cp1256`, not UTF-8.** So `gh ... > file` **decodes UTF-8 output as cp1256 and re-encodes it as UTF-8**, and every non-ASCII character becomes mojibake. This is the `gh`-on-Windows codepage corruption [#47](https://github.com/abdoupk/groundscan-analyzer-v2/issues/47) recorded; this is its mechanism, and it is silent.

Reproduction, on a body carrying **10 em-dashes**:

| path | result |
| --- | --- |
| `gh issue view 66 --json body --jq .body > f` | **0 em-dashes survive.** The file holds 96 bytes of cp1256 codepage values (`0xC2`, `0xC3`, `0xD8`, `0xB8`, `0xA4`, `0xAB`-`0xAD`, `0x94`-`0x96`, `0x80`) |
| the same, with `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` set first | **all 10 survive** |

**Three paths are safe. Reach for these.**

- **Pass non-ASCII as an _argument_**, e.g. a here-string into `--body`. **Lossless** - verified for `U+2192`, `U+2014`, `U+2013`, `U+00D7`, `U+00B2`. So `gh issue comment <n> --body $text` does not corrupt text, however the shell happens to be holding it.
- **Do the work inside `--jq` and let `gh` emit ASCII only.** `gh api ... --jq '"n=" + ((.body | split("\u2192") | length) - 1 | tostring)'` counts a character without the character ever crossing the shell. To test whether a body carries *any* non-ASCII, use `[.body | explode[] | select(. > 127)] | length`. **This is the only trustworthy way to check**, because a file read back through a redirect cannot be relied on to report its own contents correctly.
- **Read and write files with the file tools**, which go through disk and never touch console encoding. This is why editing `docs/measurements.md` with them is safe while round-tripping it through a shell is not.

**What is actually at risk** is the act of *producing* a file by redirecting `gh` output: `gh issue edit --body-file` then reads that file correctly, so a body mangled on the way out is pushed mangled, and the damage is invisible in the diff because the mangling happens before git sees it.

**Current exposure.** The map body and every ticket body closed so far are **pure ASCII** (verified: zero codepoints above 127), so their round-trips are safe by luck rather than by handling - and a session that assumed otherwise would report a false alarm, as this one nearly did. **`docs/measurements.md` is not ASCII** - 51 arrows, 76 en-dashes, 49 `×`, 3 `²` - and must never be produced by a redirect. **Its exact em-dash count is deliberately not stated here**, for the reason two paragraphs down: it was written once and drifted, and a count that can only go stale is a count to delete rather than correct. Verify the file's characters by counting them, which costs one command and cannot be wrong twice.

Three classes of claim are worth re-checking with `--jq` rather than a file, because a corrupted read and a correct one look the same: **"this figure appears nowhere"**, **"this body is complete"**, and **"this file says this"**. The first two were settled this way when [#61](https://github.com/abdoupk/groundscan-analyzer-v2/issues/61) was resolved. The third was added after a session reported a phrase in a resolution comment as bold and then nearly patched against the wrong string: **a rendered dump is not the file.** Quoting, emphasis and line breaks shown by a terminal are easy to add by eye, so assert the exact substring - or count its occurrences - before you patch against it.

**A body is not a document you read; it is a document you round-trip.** The map body is **121 KB**, larger than any terminal capture, so `gh issue view <map> --json body` truncates every time. A truncated read is not a smaller document, it is a wrong one, and it has twice produced an `edit` whose `oldString` could not be found because the text came from a cut-off view. **Reach for [`scripts/map_body.py`](../../scripts/map_body.py)** rather than reading or redirecting a body by hand.

## Shell mechanics: four things that each cost a call

**Verified 2026-10-05, PowerShell 7.** Every one of these has looked like a `gh` bug and was not.

- **Quote `@me`.** `--add-assignee @me` unquoted is splatted by PowerShell, and `gh` answers `flag needs an argument` - which reads as a `gh` version problem. Write `--add-assignee "@me"`.
- **Keep `jq` expressions to one line.** A `--jq` expression containing `\n`, nested parentheses, or an escaped quote is mangled by PowerShell before `gh` receives it, and it fails as `failed to parse jq expression` pointing at a column that looks correct. For a one-liner that emits ASCII only, `--jq` is the right tool - it counts a character without the character crossing the shell. **For anything longer, do the work in Python** and let `gh` hand back raw bytes; `scripts/map_body.py` is the worked example.
- **The comment endpoints are different paths.** The *listing* is `repos/<owner>/<repo>/issues/<n>/comments`; the *item* is `repos/<owner>/<repo>/issues/comments/<id>`, where `<id>` is the REST id from that listing. Fetching or patching the item under the listing's path returns **404**.
- **Push a body from a file with `-F "body=@file"`.** `gh api --method PATCH repos/<owner>/<repo>/issues/<n> -F "body=@file"` reads the file as the value, so the text never crosses the shell and cannot be re-encoded on the way out.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Editing the map body**: pull it, edit the file, push it, and let the tool prove the round trip - `python scripts/map_body.py pull`, then `python scripts/map_body.py push <file> --expect "## Decisions so far"`. **Never** read the body with `gh issue view`, and never produce it with `>`. The body is ~121 KB and grows every session.
- **Superseded snapshots**: `docs/wayfinder/` holds two point-in-time copies of the map, each carrying a `SUPERSEDED SNAPSHOT` banner. They are history and are watermarked with the newest ticket each reaches. **Never read one for current state** - a reader who trusts its structure finds decisions sixty tickets old and an open-ticket list whose entries are all closed.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.