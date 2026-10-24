---
name: seed-post
description: "Find the first-ever mention of any phrase on X/Twitter using archive search."
author: https://github.com/jbrck
license: MIT
platforms: [linux, macos]
card: card.png
prerequisites:
  commands: [node, python3]
  env_file: .env (AUTH_TOKEN, CT0)
---

# seed-post — Find the first mention of any phrase on X/Twitter

Given any phrase, **seed-post** finds the earliest mention on X/Twitter by searching X's full archive through its internal GraphQL API. It uses a binary-chop date narrowing algorithm to pinpoint the first appearance, then can scan mention-frequency growth over time.

## How it works

X's internal GraphQL search (accessed via the `@steipete/bird` npm CLI) supports `since:` and `until:` date operators that reach back to X's launch in 2006. seed-post uses this to:

1. **Probe existence** — is the phrase on X at all?
2. **Sweep 6-month windows** — probe consecutive half-year windows forward from 2006 to find the earliest window with mentions
3. **Binary-chop months** — within that year, find the earliest month
4. **Binary-chop days** — within that month, find the earliest day
5. **Fetch and filter** — get all tweets from that day, filter for exact substring matches, return the chronologically first
6. **Growth scan** (optional) — scan successive time windows to show mention-frequency growth

The search runs in under 60 seconds for most phrases when a rough time bound is given; a full-archive scan of a term that started years after launch is slower (one probe per 6-month window, ~2.5s apart).

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
python3 scripts/seed-post.py "bitcoin"
```

Or let it auto-install if @steipete/bird isn't present:

```bash
python3 scripts/seed-post.py --install "bitcoin"
```

## Updating

When X changes their API (query IDs go stale), update `@steipete/bird`:

```bash
npm update @steipete/bird
```

The script checks for `@steipete/bird` in `node_modules/.bin/bird` on every run. Run with `--install` to reinstall if it's missing.

## Usage

```
python3 scripts/seed-post.py <phrase> [--graph] [--annual] [--shares N] [--candidates N] [--json]

Arguments:
  phrase           The exact phrase to search for (case-insensitive)
  --graph, -g      Also run growth scan (mention frequency over time windows)
  --json, -j       Output raw JSON (machine-readable)
  --after          Only search after this date (YYYY-MM-DD, inclusive)
  --before         Only search before this date (YYYY-MM-DD, exclusive)
  --window         Growth window duration: '7d', '30d', '3m', '1y', etc.
  --annual         Calendar-year growth windows (for long-running terms)
  --shares N       Show first N early mentions after the seed post
  --candidates N   Log N displaced runner-up candidates found during the chop
  --install        Install @steipete/bird dependency if missing
```

### Examples

#### Find the first mention

```bash
python3 scripts/seed-post.py "bitcoin"
```

Output:
```
╔══════════════════════════════════════════════════════╗
║  SEED POST FOUND   first mention of "bitcoin"         ║
╠══════════════════════════════════════════════════════╣
║  @halfin                                            ║
║  Sun Jan 11 03:33:52 +0000 2009                     ║
║  https://x.com/halfin/status/1110302988             ║
╠══════════════════════════════════════════════════════╣
║  Running bitcoin                                    ║
║  ❤️ 133332  ↻ 44383  💬 11706  👁 0                  ║
╚══════════════════════════════════════════════════════╝
```

The phrase was first mentioned on X over **17 years ago**, by @halfin — one of the earliest people on the platform.

#### Full search with growth timeline

```bash
python3 scripts/seed-post.py "bitcoin" --graph
```

Shows the OG post + a bar chart of mention activity across time windows. For a 17-year-old term like "bitcoin", the growth scan reveals how the conversation evolved from @halfin's single post to today's millions of mentions.

The growth output uses a default window schedule — week 1, week 2, remainder of month 1, then month 2, month 3. Use `--window` to control the window size.

#### Annual growth view

For long-running terms, `--annual` shows each calendar year as a window:

```bash
python3 scripts/seed-post.py "bitcoin" --graph --annual
```

```
────────────────────────────────────────────────────────────
  GROWTH TIMELINE (mentions over time)
────────────────────────────────────────────────────────────

  Year   Date Range                 Count
  ─────────────────────────────────────────────────────────

  2009   Jan 11 - Dec 31               3  
  2010   Jan 1 - Dec 31                3  
  2011+  2011 onward                  40  ████████████████████████████████████████

  (13 years with 40+ posts collapsed into 1 row — API sample cap reached)

  (bar width = 40 posts = 40 chars)
```

Early years show the real count. Once mentions far exceed what X returns per query, the table collapses the saturated years into a single row with a "+" label. The script still queries every window — the display just trims the repeats for readability.

#### Search operators

The phrase isn't limited to exact-match. Pass compound queries using X's search syntax:

```bash
# Exact phrase + related terms with OR
python3 scripts/seed-post.py '"voting machine" tampering OR hack OR hijack'

# With negative terms — exclude noisy results
python3 scripts/seed-post.py '"voting machine" tampering -audit -paper'

# Using from:, has:, url:, lang: and other X operators
python3 scripts/seed-post.py '"voting machine" has:links'
```

When the phrase contains `"`, `OR`, `AND`, `-`, or any search operator (`from:`, `to:`, `url:`, `lang:`, `has:`), the script passes it through directly instead of wrapping in exact-match quotes. Everything else — `--graph`, `--shares`, `--annual`, date bounds — works the same.

#### Early mentions

```bash
python3 scripts/seed-post.py "bitcoin" --shares 5
```

Searches the 7 days after the seed post for anyone else who picked up the phrase — retweets, quote tweets, independent mentions. Shows who amplified the term first.

#### Displaced candidates

```bash
python3 scripts/seed-post.py "bitcoin" --candidates 5
```

Logs the runner-up posts from the seed post's first day that the OG post displaced. Zero extra API calls — the data comes from the same day-fetch as the seed post.

#### Get raw JSON

```bash
python3 scripts/seed-post.py "bitcoin" --json
```

Useful for piping into other tools or processing in scripts. The JSON includes `found`, `phrase`, `og_post`, and optionally `growth`, `early_shares`, and `candidates`:

### Interactive time-window prompt

Run with no flags in a terminal and seed-post asks:

```
Do you know roughly when the term first appeared?
  [1] No idea — scan the full archive (2006 to today)
  [2] It was in a specific year (e.g. 2010)
  [3] It was between two dates (e.g. 2008-03 to 2010-07)
```

Agents and scripts should NOT rely on the prompt — pass bounds explicitly instead. Any rough guess cuts the sweep dramatically. A term from 2020 found with `--after 2018-01-01` skips ~24 empty 6-month probes that a full-archive run spends before reaching the hit window.

**Where the "earliest mention" asking comes from:** seed-post's whole job is answering "when was the first mention?" The prompt above is the only human interaction — it just asks *if the caller knows a rough window* to skip wasted probes. Default (full archive) is fine, just slower: ~35+ probes for a term that started in 2014, vs ~15 with a rough bound.

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
6-month window sweep (2006 → forward, first hit)
    ↓
Month-level binary chop within winning window
    ↓
Day-level binary chop within winning month
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

X's search tokenizes queries. A search for `"bitcoin"` might return tweets
containing "bit" and "coin" as separate tokens (in some languages/contexts). The
script filters results client-side with an exact substring check
(`phrase.lower() in tweet['text'].lower()`) to ensure only true matches.

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
| @steipete/bird (npm CLI) not installed | Dependencies not installed | Run `npm install` |
| Growth scan shows 0 for all windows | Phrase is too new or too rare | The script found results in existence check but couldn't find them with exact-match filter |
| Python syntax error | Wrong Python version | Use Python 3.9+ (`python3 --version`)

## License

MIT. This project uses `@steipete/bird` (npm CLI) for X GraphQL API access.

## Related

This is part of the `skills-for-x` collection — standalone skills for X/Twitter.
More at: https://github.com/jbrck/skills-for-x