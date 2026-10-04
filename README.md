# CineSuper: Compulsory Weekend Task Guide

- Guide: https://sathishshah.github.io/cinesuper-guide/
- Task status: https://sathishshah.github.io/cinesuper-guide/status.html
- Submission form (Jotform): https://form.jotform.com/262758737111057

## How the Task Status page is updated

```
Student submits Jotform ─► GitHub Action (every 30 min) ─► tools/validate.py ─► students.json ─► status.html
                                         marks.csv / roster.csv ─┘
```

The Action `.github/workflows/update-status.yml` pulls submissions from Jotform, validates every
student and republishes `students.json`. Run it any time from **Actions → Update task status → Run workflow**.

### One-time setup: Jotform API key

1. Jotform → **My Account → API** (https://www.jotform.com/myaccount/api) → **Create New Key**, permission **Read Access**.
2. Add it as a repository secret named `JOTFORM_API_KEY`:
   - GitHub: repo **Settings → Secrets and variables → Actions → New repository secret**, or
   - Terminal: `gh secret set JOTFORM_API_KEY --repo sathishshah/cinesuper-guide`

### What is checked automatically

| Check | Fails when |
|---|---|
| Repo URL | Not `https://github.com/<user>/cinesuper-<jsoft-id>` (e.g. `cinesuper-jsoft26451`) |
| Repo | Not found or private |
| Files | Any of `index.html`, `style.css`, `config.js`, `app.js`, `README.md`, `database/01–06_*.sql`, `screenshots/` missing |
| Commits | Any of the 8 `Phase N: …` commits missing (commits after `deadline` are not counted) |
| Live URL | Not `https://<user>.github.io/<repo>/`, does not match the repo, or does not load |
| Footer | JSOFT ID not shown; placeholder text left |
| config.js | Missing, placeholder keys, or a secret / service_role key |
| Supabase | Database not answering, fewer than 18 movies or 7 genres, `movie_ratings` view missing |
| Copying | Two students share a repo or Supabase project (status becomes **Under review**) |

Status: **Completed** (all checks pass), **Under review** (passes but flagged), **Incomplete** (problems listed in Remarks), **Not submitted** (in `roster.csv` but no submission).

### Faculty files

- `marks.csv` — `jsoft,marks,remarks` (e.g. `JSOFT26451,23,Excellent work`). Add a row after evaluating a student; a faculty remark replaces the automatic remarks. Pushing this file triggers an update.
- `roster.csv` — `jsoft,name` for the whole class (built from the form's JSOFT dropdown), so students who never submit appear as **Not submitted**. Add new students here and in the form dropdown.
- `tools/config.json` — form ID, `deadline` (e.g. `"2026-10-11T23:59:00+05:30"`), max marks, minimum movies/genres.

### Running it locally

```bash
JOTFORM_API_KEY=xxxx python3 tools/validate.py
```

Run locally, it also writes `data/report.csv` with emails and full details (which students share a
repo, exposed secret keys). `data/` is git-ignored: never commit it. Public logs and `students.json`
never contain emails or names of suspected copies.
