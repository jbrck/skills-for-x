# skills-for-x

A growing collection of standalone tools for mining X/Twitter's full archive. Each tool is self-contained, open source, and runs on browser cookies — no API key, no Enterprise contract.

## Skills

| Skill | What it does |
|-------|-------------|
| [seed-post](seed-post/) | Find the first-ever mentions of any phrase on X — binary-chop archive search, growth timeline, early mentions |

*More skills coming.*

## Requirements

All skills require:

- **Node.js >= 20** (for [@steipete/bird](https://github.com/steipete/bird) — the GraphQL CLI that powers every tool in this repo)
- **Python >= 3.10**
- **X account cookies** (auth_token + ct0) — each skill documents how to get these

## Quick start

```bash
git clone https://github.com/jbrck/skills-for-x.git
cd skills-for-x/<skill-name>
npm install
# Follow the skill's README for cookie setup
```

## Why this exists

X's official API charges $200–$42,000/month for search access. The web interface shows you the latest, not the beginning. This repo gives you the same internal GraphQL endpoints that power x.com — through the excellent [@steipete/bird](https://github.com/steipete/bird) CLI — wrapped in purpose-built tools for specific investigative workflows.

## Adding a skill

Skills live in their own directory under the repo root. Each needs:

- A `README.md` (what it does, how to use it)
- A `SKILL.md` (Hermes agent skill frontmatter for AI-native execution)
- A `package.json` (npm dependency on `@steipete/bird`)
- A `.env.example` (cookie template)
- Scripts in `scripts/`

The root `README.md` skills table should be updated when a new skill is added.

## License

Skills in this repo are individually licensed. Check each skill's `SKILL.md` for its license.

## Attribution

Built by [Justin Brock](https://github.com/jbrck). Not affiliated with X Corp.