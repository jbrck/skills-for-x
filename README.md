# skills-for-x

Standalone tools for mining X/Twitter's full archive via the [@steipete/bird](https://github.com/steipete/bird) GraphQL CLI.

## Skills

| Skill | What it does |
|-------|-------------|
| [seed-post](seed-post/) | Find the first-ever mention of any phrase on X — binary-chop archive search + growth timeline |

![seed-post card](seed-post/card.svg)

## Requirements

- **Node.js >= 20** (for `@steipete/bird` — the bird CLI hits X's internal GraphQL API)
- **Python >= 3.10**
- **X account cookies** (auth_token + ct0) — each skill documents how to get these

## License

Skills in this repo are individually licensed. Check each skill's `SKILL.md` for its license.

## Attribution

Built by [Justin Brock](https://github.com/jbrck). Not affiliated with X Corp.