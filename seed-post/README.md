# seed-post

Find the first-ever mentions of any phrase on X/Twitter — binary-chop archive search + growth timeline + early mentions.

![seed-post card](card.png)

## Who is this for

**Marketers and brand managers** — track the first mention of your brand, product, or campaign on X. Useful for origin stories, PR timelines, and "we were here first" positioning.

**Crypto degens** — trace when a token, chain, or protocol first entered the conversation. (Bitcoin's first post is the built-in example.)

**Patent and trademark attorneys** — establish first-public-use dates for prior art disputes. X's archive is a timestamped public record.

**PR and crisis teams** — pinpoint when a rumor, lie, or leaked claim first appeared. Tighter correction timelines, faster takedown requests.

**Competitive intelligence** — find when a competitor first named a product category. "We were talking about this before they were."

**Product managers** — locate the first user request for a feature. Hard data for roadmap justification.

**Political and election researchers** — trace when a slogan, hashtag, or narrative entered the timeline.

**Psyop and disinformation researchers** — identify patient zero of a coordinated narrative. Pinpoint when a planted talking point first appeared and measure how long before it hit mainstream.

**Trademark litigators** — need hard timestamps at scale. The X archive carries weight in filings, and the billable tolerance for tool setup is low.

## Quick start

```bash
# 1. Install dependencies
npm install

# 2. Add your X cookies
cp .env.example .env
# Edit .env with your auth_token and ct0 from x.com

# 3. Run it
python3 scripts/seed-post.py "bitcoin"
```

## Flags

| Flag | What it does |
|------|-------------|
| `--graph` / `-g` | Show growth timeline (mention frequency over time) |
| `--annual` | Calendar-year growth windows (for long-running terms) |
| `--window 30d` | Custom window size: `7d`, `30d`, `3m`, `1y` |
| `--shares N` | Show first N early mentions after the seed post |
| `--after 2020-01-01` | Only search after this date |
| `--before 2021-01-01` | Only search before this date |
| `--json` / `-j` | Raw JSON output (machine-readable) |
| `--install` | Auto-install missing npm dependencies |

## Requirements

- Node.js >= 20 (for [@steipete/bird](https://github.com/steipete/bird) GraphQL CLI)
- Python >= 3.10
- X account cookies (auth_token + ct0)

## How it works

The script uses X's internal GraphQL API (via `@steipete/bird`) to search the full archive back to 2006. It binary-chops by year → month → day, filters exact matches client-side, and returns the chronologically first post. The growth scan probes time windows from the OG post date to today. The early mentions scan finds who picked up the term in the week after the seed post.

## X search operators

Seed-post passes your query directly to X's GraphQL API. You can include any X search operator in your phrase to narrow results.

### Filter by account

| Operator | Example | What it does |
|----------|---------|-------------|
| `from:username` | `from:halfin bitcoin` | Posts from a specific user |
| `to:username` | `to:halfin bitcoin` | Posts replying to a specific user |
| `@username` | `@halfin bitcoin` | Posts mentioning a specific user |

### Filter by content type

| Operator | Example | What it does |
|----------|---------|-------------|
| `has:images` | `bitcoin has:images` | Posts with images |
| `has:videos` | `bitcoin has:videos` | Posts with videos |
| `has:media` | `bitcoin has:media` | Posts with any media |
| `has:links` | `bitcoin has:links` | Posts containing a link |
| `has:hashtags` | `bitcoin has:hashtags` | Posts with hashtags |
| `has:mentions` | `bitcoin has:mentions` | Posts with @mentions |
| `-` (minus) | `bitcoin -ethereum` | Exclude posts matching a term |
| `lang:LANG` | `bitcoin lang:en` | Posts in a specific language |

### Filter by engagement

| Operator | Example | What it does |
|----------|---------|-------------|
| `min_replies:N` | `bitcoin min_replies:10` | Posts with at least N replies |
| `min_likes:N` | `bitcoin min_likes:50` | Posts with at least N likes |
| `min_retweets:N` | `bitcoin min_retweets:5` | Posts with at least N retweets |

### Filter by URL

| Operator | Example | What it does |
|----------|---------|-------------|
| `url:domain.com` | `bitcoin url:coinbase.com` | Posts containing a link to a domain |

### Examples with operators

```bash
# First bitcoin mention from a specific account
python3 scripts/seed-post.py "bitcoin from:halfin"

# Exact phrase + required word
python3 scripts/seed-post.py '"voting machine" tampering'

# OR queries
python3 scripts/seed-post.py '"voting machine" OR "election fraud"'

# With negative terms
python3 scripts/seed-post.py '"voting machine" -paper'

# With operators
python3 scripts/seed-post.py '"voting machine" tampering has:links'

# First mention with a link
python3 scripts/seed-post.py "AI agents has:links"

# First English mention, excluding a related term
python3 scripts/seed-post.py "quantum computing lang:en -crypto"

# First mention with at least some engagement
python3 scripts/seed-post.py "psyop min_replies:3"
```

Note: `since:` and `until:` are handled internally by the `--after`/`--before` flags. Don't include them in your query — use the flags instead.

For the full list of X search operators, see [X's search page](https://x.com/search-advanced) or the [unofficial operator reference](https://github.com/steipete/bird).

## License

MIT