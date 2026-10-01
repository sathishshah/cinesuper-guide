# CineSuper: Compulsory Weekend Task Guide

Live guide: https://sathishshah.github.io/cinesuper-guide/

## Adding a student to "Completed students"

After verifying a student's 8 commits and live link, add an entry to `students.json` and commit:

```json
[
  {
    "name": "Ravi Kumar",
    "regno": "24CS045",
    "live": "https://ravi-cse24.github.io/cinesuper-24cs045/",
    "repo": "https://github.com/ravi-cse24/cinesuper-24cs045"
  }
]
```

- Separate entries with commas; the file must stay valid JSON.
- Links must start with `https://`, otherwise they are hidden.
- The list is sorted by register number automatically.
- You can edit the file directly on GitHub (pencil icon); the site updates in 1 to 2 minutes.
