# CineSuper: Compulsory Weekend Task Guide

- Guide: https://sathishshah.github.io/cinesuper-guide/
- Task status: https://sathishshah.github.io/cinesuper-guide/status.html

## Updating the Task Status page

Edit `students.json` (on GitHub: open the file → pencil icon → Commit changes). The site updates in 1 to 2 minutes.

```json
{
  "updated": "6 Oct 2026",
  "maxMarks": 25,
  "students": [
    {
      "name": "Ravi Kumar",
      "regno": "24CS045",
      "status": "Completed",
      "commits": 8,
      "marks": 23,
      "live": "https://ravi-cse24.github.io/cinesuper-24cs045/",
      "repo": "https://github.com/ravi-cse24/cinesuper-24cs045",
      "remarks": "Excellent watchlist feature"
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `name` | yes | Student's name |
| `regno` | yes | Register number; default sort order |
| `status` | yes | `Completed`, `Under review`, `Incomplete` or `Not submitted` |
| `commits` | no | Number of checkpoint commits found (0–8) |
| `marks` | no | Leave out (or `null`) until awarded; decimals allowed |
| `live`, `repo` | no | Must start with `https://`, otherwise hidden |
| `remarks` | no | Short note shown in the table |

- Separate students with commas; the file must stay valid JSON (check at https://jsonlint.com if the page shows no students).
- `updated` is shown as "Last updated" under the heading.
