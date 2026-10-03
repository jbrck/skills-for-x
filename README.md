# skills-for-x

Standalone tools for mining X/Twitter's full archive via the [@steipete/bird](https://github.com/steipete/bird) GraphQL CLI.

## Skills

| Skill | What it does |
|-------|-------------|
| [seed-post](seed-post/) | Find the first-ever mention of any phrase on X — binary-chop archive search + growth timeline |

![seed-post card](seed-post/card.svg)

## Who is this for

**Marketers and brand managers** — track the first mention of your brand, product, or campaign on X. Useful for origin stories, PR timelines, and "we were here first" positioning.

**Crypto degens** — trace when a token, chain, or protocol first entered the conversation. (Bitcoin's first post is the built-in example.)

**Patent and trademark attorneys** — establish first-public-use dates for prior art disputes. X's archive is a timestamped public record.

**PR and crisis teams** — pinpoint when a rumor, lie, or leaked claim first appeared. Tighter correction timelines, faster takedown requests.

**Competitive intelligence** — find when a competitor first named a product category. "We were talking about this before they were."

**Product managers** — locate the first user request for a feature. Hard data for roadmap justification.

**Political and election researchers** — trace when a slogan, hashtag, or narrative entered the timeline.

**Trademark litigators** — need hard timestamps at scale. The X archive carries weight in filings, and the billable tolerance for tool setup is low.

## Requirements

- **Node.js >= 20** (for `@steipete/bird` — the bird CLI hits X's internal GraphQL API)
- **Python >= 3.10**
- **X account cookies** (auth_token + ct0) — each skill documents how to get these

## License

Skills in this repo are individually licensed. Check each skill's `SKILL.md` for its license.

## Attribution

Built by [Justin Brock](https://github.com/jbrck). Not affiliated with X Corp.