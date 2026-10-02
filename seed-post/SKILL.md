---
name: seed-post
description: "Find the first-ever mention of any phrase on X/Twitter using archive search."
author: https://github.com/jbrck
license: MIT
platforms: [linux, macos]
prerequisites:
  commands: [node, python3]
  env_file: .env (AUTH_TOKEN, CT0)
---

# seed-post — Find the first mention of any phrase on X/Twitter

Given any phrase, **seed-post** finds the earliest mention on X/Twitter by searching X's full archive through its internal GraphQL API. It uses a binary-chop date narrowing algorithm to pinpoint the first appearance, then can scan mention-frequency growth over time.

## How it works

X's internal GraphQL search (accessed via the `@steipete/bird` npm CLI) supports `since:` and `until:` date operators that reach back to X's launch in 2006. seed-post uses this to:

1. **Probe existence** — is the phrase on X at all?
2. **Binary-chop years** — walk backward from the current year to find the earliest year with mentions
3. **Binary-chop months** — within that year, find the earliest month
4. **Binary-chop days** — within that month, find the earliest day
5. **Fetch and filter** — get all tweets from that day, filter for exact substring matches, return the chronologically first
6. **Growth scan** (optional) — scan successive time windows to show mention-frequency growth

The entire search runs in under 60 seconds for most phrases.

## Setup

### 1. Install dependencies

- **Node.js** >= 20 (for `@steipete/bird`)
- **Python** >= 3.9
- **npm** (ships with Node.js)

### 2. Install @steipete/bird

```bash
npm install
```

This installs the `@steipete/bird` CLI — X's internal GraphQL API client. The script will also auto-install it with `--install` if missing.

### 3. Get your X session cookies

The CLI needs your browser session cookies to authenticate:

1. Open `x.com` in Chrome/Firefox while logged in
2. Open Developer Tools → Cookies → `x.com`
3. Copy the values for `auth_token` and `ct0`

### 4. Create .env file

```bash
cp .env.example .env
```

Edit `.env` and paste your cookie values:

```
AUTH_TOKEN=your_auth_token_here
CT0=your_ct0_csrf_token_here
```

**Important:** Keep this file secret. Never commit it to git. `.env` is in `.gitignore`.

### 5. Verify it works

```bash
python3 scripts/seed-post.py "hyperqwen"
```

Or let it auto-install if @steipete/bird isn't present:

```bash
python3 scripts/seed-post.py --install "hyperqwen"
```

## Updating

When X changes their API (query IDs go stale), update `@steipete/bird`:

```bash
npm update @steipete/bird
```

The script checks for `@steipete/bird` in `node_modules/.bin/bird` on every run. Run with `--install` to reinstall if it's missing.

## Usage

```
python3 scripts/seed-post.py <phrase> [--graph] [--json]

Arguments:
  phrase       The exact phrase to search for (case-insensitive)
  --graph, -g  Also run growth scan (mention frequency over time windows)
  --json, -j   Output raw JSON (machine-readable)
```

### Examples

#### Find the first mention

```bash
python3 scripts/seed-post.py "hyperqwen"
```

Output:
```
────────────────────────────────────────────────────────────
  SEED POST FOUND
────────────────────────────────────────────────────────────

  Author:    @sorek_UK (Rob Wijnhoven)
  Date:      Tue Sep 22 18:57:27 +0000 2026
  Link:      https://x.com/sorek_UK/status/2102472361895235727

  Running HyperQwen 27B on my single 4090D 4x 160k context size...

  ❤️ 2  🔁 0  💬 2  👁 0
```

#### Full search with growth timeline

```bash
python3 scripts/seed-post.py "hyperqwen" --graph
```

Shows the OG post + a bar chart of mention activity across time windows:

```
────────────────────────────────────────────────────────────
  GROWTH TIMELINE (mentions over time)
────────────────────────────────────────────────────────────

  Week 1 (first 7 days)          │  12  ████████████████
  Week 2                         │   8  ██████████
  Remainder of Month 1           │   3  ████
  Month 2                        │  45  ████████████████████████████████████████████
  Month 3                        │   0
```

#### Get raw JSON

```bash
python3 scripts/seed-post.py "hyperqwen" --json
```

Useful for piping into other tools or processing in scripts.

## Project structure

```
seed-post/
├── SKILL.md                     # This file — docs + skill definition
├── package.json                 # npm dependency: @steipete/bird
├── .env.example                 # Template for cookie setup
├── .gitignore                   # Ignores .env and node_modules/
├── node_modules/                # Installed by npm (not committed)
└── scripts/
    └── seed-post.py             # Main script — binary-chop + growth scan
```

## Algorithm details

### Binary-chop date narrowing

```
Broad existence probed in one query
    ↓
Year-level scan (current year → 2006, backward)
    ↓
Month-level scan within winning year
    ↓
Day-level binary chop within winning month
    ↓
Linear backward scan to confirm first day
    ↓
Fetch all tweets from the confirmed day
    ↓
Filter for exact substring matches
    ↓
Sort by createdAt, return earliest
```

### Growth window schedule

```
Week 1:  D → D+7      (first 7 days)
Week 2:  D+7 → D+14   (days 8-14)
Remainder of Month 1:  D+14 → D+30
Month N:   30-day rolling windows until today
```

### Exact-match filtering

X's search tokenizes queries. A search for `"hyperqwen"` returns tweets containing "hyper" AND "qwen" as separate tokens, including posts mentioning "Qwen" without "HyperQwen". The script filters results client-side with an exact substring check (`phrase.lower() in tweet['text'].lower()`) to ensure only true matches.

### Rate limiting

The script spaces queries 2.5 seconds apart to avoid triggering X's rate limits. A full search with growth scan makes ~30-50 API calls and takes 1-3 minutes.

## Limitations

- **Token-level search, not substring** — X's search matches tokens, not substrings. Client-side filtering catches most false positives but may miss edge cases.
- **Cookie expiration** — AUTH_TOKEN/CT0 expire every few weeks. When results stop working, re-paste fresh cookies.
- **Result cap** — bird-search returns ~20-60 results per query. For very high-volume phrases, the raw count per window is directional rather than exact. The growth bar chart's scale is normalized to the busiest window.
- **Deleted/private tweets** — Not indexed by X's search. We'll miss them.
- **Link-card matching** — Tweets with only a link can match via the link preview card's metadata. The exact-match filter catches most of these by requiring the phrase in tweet text.
- **No Google fallback** — This script uses only X's GraphQL API. It won't work without valid X cookies.

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| "No mentions found" for a known phrase | Cookies expired | Re-paste AUTH_TOKEN/CT0 |
| Script exits with "session error" | X rate-limited the IP | Wait 5 minutes and retry |
| "bird-search.mjs not found" | Wrong working directory | Run from the `seed-post/` directory |
| Growth scan shows 0 for all windows | Phrase is too new or too rare | The script found results in existence check but couldn't find them with exact-match filter |
| Python syntax error | Wrong Python version | Use Python 3.9+ (`python3 --version`)

## License

MIT. This project vendors `bird-search.mjs` from the `last30days` project by mvanhorn (originally `@steipete/bird` by Peter Steinberger), also MIT licensed.

## Related

This is part of the `skills-for-x` collection — standalone skills for X/Twitter.
More at: https://github.com/jbrck/skills-for-x