#!/usr/bin/env python3
"""Validate CineSuper submissions and rebuild students.json for the Task Status page.

Submissions come from Jotform:
  * JOTFORM_API_KEY set  -> fetched from the Jotform API (used by the GitHub Action)
  * otherwise            -> read from data/submissions.json (list of submission objects)

For every student (latest submission per register number) it checks:
  repo URL format, repo is public, required files, the 8 phase commits before the
  deadline, live URL format and owner, live site loads with the student's reg no,
  config.js holds a public (not secret) Supabase key, and the student's Supabase
  database answers with the expected data. It also flags shared repos / Supabase
  projects between students.

Marks come from marks.csv (regno,marks,remarks) entered by faculty.
Nothing private (emails) is written to students.json or printed.
"""
import base64, csv, json, os, re, subprocess, sys, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = json.load(open(os.path.join(ROOT, "tools", "config.json")))
REQUIRED_PHASES = {0: "repo setup", 3: "create tables", 4: "sample data", 5: "RLS policies",
                   6: "view and queries", 8: "frontend", 11: "README and live link", 12: "personalisation"}
REQUIRED_FILES = ["README.md", "index.html", "style.css", "config.js", "app.js",
                  "database/01_tables.sql", "database/02_seed.sql", "database/03_security.sql",
                  "database/04_view.sql", "database/05_queries.sql", "database/06_personalisation.sql"]
UA = {"User-Agent": "cinesuper-validator"}


# ---------- HTTP helpers ----------
def http(url, headers=None, timeout=20):
    """Return (status, headers, body_text). Network errors give status 0."""
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read().decode("utf-8", "replace")
    except Exception as e:  # DNS, timeout, TLS ...
        return 0, {}, str(e)


def github_token():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


GH_TOKEN = github_token()


def gh(path):
    headers = {"Accept": "application/vnd.github+json"}
    if GH_TOKEN:
        headers["Authorization"] = "Bearer " + GH_TOKEN
    status, _, body = http("https://api.github.com" + path, headers)
    try:
        return status, json.loads(body)
    except ValueError:
        return status, None


# ---------- Submissions ----------
def load_submissions():
    key = os.environ.get("JOTFORM_API_KEY")
    if key:
        base = os.environ.get("JOTFORM_API_BASE", "https://api.jotform.com")
        url = f"{base}/form/{CONFIG['jotformFormId']}/submissions?" + urllib.parse.urlencode(
            {"apiKey": key, "limit": 1000, "orderby": "created_at"})
        status, _, body = http(url)
        if status != 200:
            sys.exit(f"Jotform API error {status}")
        raw = json.loads(body).get("content", [])
    else:
        path = os.path.join(ROOT, "data", "submissions.json")
        if not os.path.exists(path):
            print("No JOTFORM_API_KEY and no data/submissions.json; nothing to validate.")
            return []
        raw = json.load(open(path))
    return [normalise(s) for s in raw if s.get("status", "ACTIVE") in ("ACTIVE", "CUSTOM", None)]


def answer_text(a):
    v = a.get("answer", a.get("prettyFormat", ""))
    if isinstance(v, dict):  # full name widget {first, last}
        v = " ".join(str(x) for x in v.values() if x)
    if isinstance(v, list):
        v = " ".join(map(str, v))
    return str(v or "").strip()


def normalise(sub):
    """Map a Jotform submission (API format) or an already-flat dict to our fields."""
    if "answers" not in sub:
        return {k: str(sub.get(k, "")).strip() for k in ("name", "regno", "email", "github", "repo", "live", "submitted_at")}
    out = {"submitted_at": sub.get("created_at", "")}
    for a in sub["answers"].values():
        label = (a.get("text") or "").lower()
        val = answer_text(a)
        if not val:
            continue
        if "register" in label:
            out["regno"] = val
        elif "repository" in label:
            out["repo"] = val
        elif "pages" in label or "live" in label:
            out["live"] = val
        elif "username" in label:
            out["github"] = val
        elif "email" in label:
            out["email"] = val
        elif "name" in label:
            out["name"] = val
    return out


# ---------- Checks ----------
def jwt_role(key):
    parts = key.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        return payload.get("role")
    except Exception:
        return None


def supabase_count(base, key, table):
    headers = {"apikey": key, "Prefer": "count=exact", "Range": "0-0"}
    if not key.startswith("sb_"):
        headers["Authorization"] = "Bearer " + key
    status, h, _ = http(f"{base.rstrip('/')}/rest/v1/{table}?select=*", headers)
    rng = {k.lower(): v for k, v in h.items()}.get("content-range", "")
    if status in (200, 206) and "/" in rng:
        total = rng.split("/")[-1]
        return int(total) if total.isdigit() else None
    return None


def validate(s, deadline):
    regno = re.sub(r"\s+", "", s.get("regno", "")).upper()
    expected_repo = "cinesuper-" + regno.lower()
    problems, warnings = [], []
    result = {"name": s.get("name", "").strip(), "regno": regno, "email": s.get("email", ""), "repo": "",
              "live": "", "commits": 0, "supabase": None, "private": []}

    # Repo URL
    m = re.match(r"^https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$", s.get("repo", "").strip())
    owner = repo = None
    if not m:
        problems.append("Repo URL is not https://github.com/<user>/<repo>")
    else:
        owner, repo = m.group(1), m.group(2)
        result["repo"] = f"https://github.com/{owner}/{repo}"
        if repo.lower() != expected_repo:
            problems.append(f"Repo must be named {expected_repo}")
        status, info = gh(f"/repos/{owner}/{repo}")
        if status != 200 or not info:
            problems.append("Repo not found or not public")
            owner = None
        elif info.get("private"):
            problems.append("Repo is private")

    # Files and commits
    if owner:
        branch = info.get("default_branch", "main")
        status, tree = gh(f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
        paths = {t["path"] for t in (tree or {}).get("tree", [])} if status == 200 else set()
        missing = [f for f in REQUIRED_FILES if f not in paths]
        if not any(p.startswith("screenshots/") for p in paths):
            missing.append("screenshots/")
        if missing:
            problems.append("Missing files: " + ", ".join(missing[:4]) + (" …" if len(missing) > 4 else ""))

        found, late, page = set(), set(), 1
        while page <= 5:
            status, commits = gh(f"/repos/{owner}/{repo}/commits?per_page=100&page={page}")
            if status != 200 or not commits:
                break
            for c in commits:
                msg = c["commit"]["message"].strip()
                pm = re.match(r"phase\s*(\d+)\b", msg, re.I)
                if not pm or int(pm.group(1)) not in REQUIRED_PHASES:
                    continue
                when = datetime.fromisoformat(c["commit"]["committer"]["date"].replace("Z", "+00:00"))
                (late if deadline and when > deadline else found).add(int(pm.group(1)))
            page += 1
        result["commits"] = len(found)
        absent = [p for p in REQUIRED_PHASES if p not in found]
        if absent:
            problems.append("Missing commits: " + ", ".join(f"Phase {p}" for p in absent))
        if late - found:
            warnings.append("Commits after deadline: " + ", ".join(f"Phase {p}" for p in sorted(late - found)))

    # Live URL
    live = s.get("live", "").strip()
    lm = re.match(r"^https://([A-Za-z0-9-]+)\.github\.io/([A-Za-z0-9._-]+)/?$", live)
    if not lm:
        problems.append("Live URL is not https://<user>.github.io/<repo>/")
    else:
        live = live.rstrip("/") + "/"
        result["live"] = live
        if m and (lm.group(1).lower() != m.group(1).lower() or lm.group(2).lower() != m.group(2).lower()):
            problems.append("Live URL does not match the repo")
        status, _, page_html = http(live)
        if status != 200:
            problems.append(f"Live site not loading (HTTP {status or 'error'})")
        else:
            low = page_html.lower()
            if regno.lower() not in low:
                problems.append("Reg no not shown on live site footer")
            if "<strong>your name</strong>" in low or "<strong>reg no</strong>" in low:
                warnings.append("Footer still has placeholder text")
            if "config.js" not in low or "supabase" not in low:
                problems.append("Live site is missing the Supabase or config.js script")
            cstatus, _, cfg = http(live + "config.js")
            url_m = re.search(r"SUPABASE_URL\s*=\s*[\"'`]([^\"'`]+)", cfg or "")
            key_m = re.search(r"SUPABASE_KEY\s*=\s*[\"'`]([^\"'`]+)", cfg or "")
            if cstatus != 200 or not url_m or not key_m:
                problems.append("config.js not found on live site")
            elif "YOUR-" in url_m.group(1) or "YOUR-" in key_m.group(1):
                problems.append("config.js still has placeholder keys")
            else:
                sb_url, sb_key = url_m.group(1).strip(), key_m.group(1).strip()
                result["supabase"] = sb_url.rstrip("/").lower()
                if sb_key.startswith("sb_secret_") or jwt_role(sb_key) == "service_role":
                    problems.append("Wrong Supabase key type in config.js (use the publishable/anon key)")
                    result["private"].append("SECRET Supabase key exposed: student must rotate it")
                movies = supabase_count(sb_url, sb_key, "movies")
                genres = supabase_count(sb_url, sb_key, "genres")
                ratings = supabase_count(sb_url, sb_key, "movie_ratings")
                if movies is None:
                    problems.append("Supabase not answering (paused project, wrong key or missing policy)")
                else:
                    if movies < CONFIG["minMovies"]:
                        problems.append(f"Only {movies} movies; need {CONFIG['minMovies']} (13 sample + 5 own)")
                    if genres is not None and genres < CONFIG["minGenres"]:
                        problems.append(f"Only {genres} genres; add a new genre")
                    if ratings is None:
                        problems.append("movie_ratings view missing or not readable")
    result["problems"], result["warnings"] = problems, warnings
    return result


# ---------- Main ----------
def main():
    deadline = None
    if CONFIG.get("deadline"):
        deadline = datetime.fromisoformat(CONFIG["deadline"])
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

    latest = {}
    for s in load_submissions():
        reg = re.sub(r"\s+", "", s.get("regno", "")).upper()
        if reg and (reg not in latest or s.get("submitted_at", "") >= latest[reg].get("submitted_at", "")):
            latest[reg] = s

    marks = {}
    mpath = os.path.join(ROOT, "marks.csv")
    if os.path.exists(mpath):
        for row in csv.DictReader(open(mpath, newline="", encoding="utf-8-sig")):
            reg = re.sub(r"\s+", "", row.get("regno", "")).upper()
            if reg:
                marks[reg] = row

    results = [validate(s, deadline) for s in latest.values()]

    # Same repo or same Supabase project used by two students
    for field, label in (("repo", "repo"), ("supabase", "Supabase project")):
        seen = {}
        for r in results:
            if r.get(field):
                seen.setdefault(r[field].lower(), []).append(r["regno"])
        for r in results:
            others = [x for x in seen.get((r.get(field) or "").lower(), []) if x != r["regno"]]
            if others:
                r["warnings"].append(f"Shares a {label} with another student")
                r["private"].append(f"Same {label} as {', '.join(others)}")

    students = []
    for r in results:
        if r["problems"]:
            status = "Incomplete"
        elif r["warnings"]:
            status = "Under review"
        else:
            status = "Completed"
        mk = marks.get(r["regno"], {})
        entry = {"name": r["name"], "regno": r["regno"], "status": status, "commits": r["commits"],
                 "live": r["live"], "repo": r["repo"]}
        if mk.get("marks", "").strip():
            entry["marks"] = float(mk["marks"]) if "." in mk["marks"] else int(mk["marks"])
        remarks = mk.get("remarks", "").strip() or " · ".join(r["problems"] + r["warnings"])
        if remarks:
            entry["remarks"] = remarks
        students.append(entry)
        detail = "; ".join(r["problems"] + r["warnings"] + r["private"]) or "all checks passed"
        r["status"], r["detail"] = status, detail
        public = "; ".join(r["problems"] + r["warnings"]) or "all checks passed"
        # Actions logs are public: print only what students.json already shows
        print(f"{r['regno']:<12} {status:<13} commits {r['commits']}/8  {public if os.environ.get('GITHUB_ACTIONS') else detail}")

    # Roster students who never submitted
    rpath = os.path.join(ROOT, "roster.csv")
    if os.path.exists(rpath):
        for row in csv.DictReader(open(rpath, newline="", encoding="utf-8-sig")):
            reg = re.sub(r"\s+", "", row.get("regno", "")).upper()
            if reg and reg not in latest:
                entry = {"name": row.get("name", "").strip(), "regno": reg, "status": "Not submitted", "commits": 0}
                mk = marks.get(reg, {})
                if mk.get("marks", "").strip():
                    entry["marks"] = float(mk["marks"]) if "." in mk["marks"] else int(mk["marks"])
                students.append(entry)

    # Private faculty report (includes emails); data/ is git-ignored and never published
    if not os.environ.get("GITHUB_ACTIONS"):
        os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
        with open(os.path.join(ROOT, "data", "report.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["regno", "name", "email", "status", "commits", "repo", "live", "details"])
            for r in sorted(results, key=lambda x: x["regno"]):
                w.writerow([r["regno"], r["name"], r["email"], r["status"], r["commits"], r["repo"], r["live"], r["detail"]])

    students.sort(key=lambda x: x["regno"])
    out = {"updated": datetime.now(timezone.utc).astimezone().strftime("%d %b %Y, %I:%M %p") if students else "",
           "maxMarks": CONFIG.get("maxMarks", 25), "students": students}
    old = {}
    try:
        old = json.load(open(os.path.join(ROOT, "students.json")))
    except Exception:
        pass
    if old.get("students") == students and old.get("maxMarks") == out["maxMarks"]:
        print("No changes to students.json")
        return
    with open(os.path.join(ROOT, "students.json"), "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"students.json updated: {len(students)} students")


if __name__ == "__main__":
    main()
