# seed-post

Find the first-ever mentions of any phrase on X/Twitter — binary-chop archive search + growth timeline + early mentions.

![Seed post in terminal output — the first bitcoin tweet by @halfin on Jan 11, 2009 at 03:33 UTC. Shows the tweet card, growth timeline bar chart, and early mentions section. Black background, white/green terminal aesthetic.](card.png)

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

Seed-post passes your query directly to X's GraphQL API. You can include any [X search operator](https://docs.x.com/x-api/posts/search/integrate/operators) in your phrase to narrow results.

### Keyword and phrase

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `keyword` | standalone | Tokenized match in post body | `pepsi OR cola` |
| `"exact phrase"` | standalone | Exact phrase match in post body | `"voting machine" tampering` |
| `emoji` | standalone | Match emoji in post body | `(😃 OR 😡) 😬` |

### Entity operators

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `#` | standalone | Match a hashtag (exact) | `#thankunext #fanart` |
| `@` | standalone | Match a username mention | `@XDevelopers` |
| `$` | standalone | Match a cashtag | `$twtr OR $btc` |

### User operators

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `from:username` | standalone | Posts from a specific user | `from:halfin` |
| `to:username` | standalone | Posts in reply to a specific user | `to:XDevelopers` |
| `retweets_of:username` | standalone | Retweets of a specific user | `retweets_of:twitterdev` |

### Post type

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `is:retweet` | conjunction required | Match retweets | `bitcoin is:retweet` |
| `is:reply` | conjunction required | Match replies | `from:XDevelopers is:reply` |
| `is:quote` | conjunction required | Match quote tweets | `"voting machine" is:quote` |
| `is:verified` | conjunction required | Posts from verified accounts | `#nowplaying is:verified` |
| `-is:nullcast` | conjunction required | Exclude promotional posts | `"mobile games" -is:nullcast` |

### Content type

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `has:hashtags` | conjunction required | Posts with hashtags | `from:XDevelopers -has:hashtags` |
| `has:cashtags` | conjunction required | Posts with cashtags | `#stonks has:cashtags` |
| `has:links` | conjunction required | Posts with links | `from:XDevelopers has:links` |
| `has:mentions` | conjunction required | Posts with @mentions | `#nowplaying has:mentions` |
| `has:media` | conjunction required | Posts with media (photo/GIF/video) | `(kittens OR puppies) has:media` |
| `has:images` | conjunction required | Posts with images | `#meme has:images` |
| `has:video_link` | conjunction required | Posts with native X videos | `#icebucketchallenge has:video_link` |
| `has:geo` | conjunction required | Posts with geolocation | `#paris has:geo` |

### Engagement

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `min_replies:N` | standalone | At least N replies | `from:XDevelopers min_replies:10` |
| `min_likes:N` | standalone | At least N likes | `#SuperBowl min_likes:100` |
| `min_reposts:N` | standalone | At least N reposts | `"breaking news" min_reposts:50` |

Note: the API uses `min_likes:` and `min_reposts:`, not `min_faves:` or `min_retweets:` (those are web-only aliases and will be rejected by the API).

### URL

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `url:domain.com` | standalone | Posts linking to a domain | `bitcoin url:coinbase.com` |

### Language

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `lang:LANG` | conjunction required | Posts in a language | `bitcoin lang:en` |

BCP 47 codes: `en`, `es`, `fr`, `de`, `ja`, `zh-CN`, `zh-TW`, `ar`, `ru`, `pt`, `it`, `nl`, `ko`, `hi`, `tr`, and [40+ more](https://docs.x.com/x-api/posts/search/integrate/operators#supported-languages).

### Location

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `place:"name"` | standalone | Posts tagged with a location | `place:"new york city"` |
| `place_country:CODE` | standalone | Posts in a country code | `place_country:US` |
| `point_radius:[lat lng radius]` | standalone | Posts within a radius | `point_radius:[2.355128 48.861118 16km]` |
| `bounding_box:[sw_lat sw_lng ne_lat ne_lng]` | standalone | Posts in a bounding box | `bounding_box:[-105.3 39.96 -105.17 40.09]` |

### Post reference

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `retweets_of_tweet_id:N` | standalone | Retweets of a specific post | `retweets_of_tweet_id:1539382664746020864` |
| `quotes_of_tweet_id:N` | standalone | Quote tweets of a specific post | `quotes_of_tweet_id:1539382664746020864` |
| `in_reply_to_tweet_id:N` | standalone | Replies to a specific post | `in_reply_to_tweet_id:1539382664746020864` |
| `conversation_id:N` | standalone | Posts in a conversation thread | `conversation_id:1334987486343299072` |

### List and context

| Operator | Type | What it does | Example |
|----------|------|-------------|---------|
| `list:N` | standalone | Posts from a List's members | `list:123` |
| `context:DOMAIN.ID` | standalone | Match a domain/entity pair | `context:10.799022225751871488` |
| `entity:"value"` | standalone | Match an entity string value | `entity:"Michael Jordan"` |

### Logical operators

| Operator | What it does |
|----------|-------------|
| `OR` | Logical OR between expressions |
| Space | Logical AND (both required) |
| `()` | Grouping for complex expressions |
| `-` | Negation/exclusion |

### Query limits

| Access | Characters |
|--------|-----------|
| API (self-serve) | 512 (recent) / 1,024 (full archive) |
| API (enterprise) | 4,096 |

### Complete examples

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

# First mention with engagement
python3 scripts/seed-post.py "psyop min_replies:3"

# First verified post on a topic
python3 scripts/seed-post.py "bitcoin is:verified"
```

Note: `since:` and `until:` are handled internally by the `--after`/`--before` flags. Don't include them in your query — use the flags instead.

## License

MIT