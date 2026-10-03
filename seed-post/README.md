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

## License

MIT