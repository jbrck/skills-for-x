#!/usr/bin/env python3
"""
seed-post.py — Find the first mention of a phrase on X/Twitter.

Uses @steipete/bird (npm CLI) to search X's internal GraphQL API.
Binary-chops date ranges to pinpoint the earliest mention, then
scans growth in successive time windows.

Usage:
  python seed-post.py "hyperqwen"
  python seed-post.py "hyperqwen" --graph
  python seed-post.py "hyperqwen" --json

Requires:
  - Node.js >= 20 (for @steipete/bird npm package)
  - AUTH_TOKEN and CT0 cookies from x.com in a .env file

License: MIT
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
NODE_MODULES = PROJECT_DIR / "node_modules"
BIRD_BIN = NODE_MODULES / ".bin" / "bird"

ENV_FILE_CANDIDATES = [
    PROJECT_DIR / ".env",
    Path.home() / ".config" / "last30days" / ".env",
    Path.cwd() / ".env",
]

BIRD_SEARCH_MIN_COUNT = 3
BIRD_SEARCH_MAX_COUNT = 60
QUERY_DELAY = 2.5
X_LAUNCH_YEAR = 2006


# ── Bird-search installation ───────────────────────────────────────────

def bird_is_installed() -> bool:
    """Check if @steipete/bird is installed in project node_modules."""
    return BIRD_BIN.exists()


def install_bird() -> bool:
    """Install @steipete/bird via npm. Returns True on success."""
    print("  Installing @steipete/bird via npm...", file=sys.stderr)
    result = subprocess.run(
        ["npm", "install", "@steipete/bird"],
        capture_output=True, text=True, timeout=60,
        cwd=str(PROJECT_DIR),
    )
    if result.returncode != 0:
        print(f"  Install failed: {result.stderr.strip()}", file=sys.stderr)
        return False
    print("  Done.", file=sys.stderr)
    return True


# ── Credentials ────────────────────────────────────────────────────────

def load_credentials() -> tuple:
    """Load AUTH_TOKEN and CT0 from env files. Returns (auth, ct0)."""
    env_vars = {}
    for f in ENV_FILE_CANDIDATES:
        if f.exists():
            for line in f.read_text().splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

    auth = env_vars.get("AUTH_TOKEN")
    ct0 = env_vars.get("CT0")
    if not auth or not ct0:
        raise FileNotFoundError(
            "AUTH_TOKEN and CT0 must be set in a .env file.\n"
            "Copy .env.example to .env and paste your x.com cookies.\n"
            "Files checked:\n  " + "\n  ".join(str(p) for p in ENV_FILE_CANDIDATES)
        )
    return auth, ct0


# ── Bird-search runner ────────────────────────────────────────────────

def run_bird(query: str, count: int, auth: str, ct0: str) -> list:
    """Run @steipete/bird search. Returns list of tweet dicts or empty list."""
    cmd = [
        str(BIRD_BIN), "--auth-token", auth, "--ct0", ct0,
        "search", query,
        "--count", str(count), "--json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        print("  [timeout]", file=sys.stderr)
        return []

    if result.returncode != 0 or not result.stdout.strip():
        err = result.stderr.strip()[:200]
        if err:
            print(f"  [{err}]", file=sys.stderr)
        return []

    try:
        tweets = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    return tweets if isinstance(tweets, list) else []


def exact_match(phrase: str, tweet: dict) -> bool:
    """Case-insensitive exact substring check."""
    return phrase.lower() in tweet.get("text", "").lower()


def parse_timestamp(created_at: str) -> datetime.datetime:
    """Parse bird createdAt string. e.g. 'Tue Sep 22 18:57:27 +0000 2026'"""
    parts = created_at.strip().split()
    if parts[0] in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        parts = parts[1:]
    return datetime.datetime.strptime(
        " ".join(parts), "%b %d %H:%M:%S %z %Y"
    )


def fmt_date(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def today_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


# ── Core: Binary-chop date search ─────────────────────────────────────

def probe_range(phrase: str, since_str: str, until_str: str,
                auth: str, ct0: str) -> int:
    """Return result count for phrase in a date range. 0 = none/error."""
    time.sleep(QUERY_DELAY)
    query = f'"{phrase}" {since_str} {until_str}'
    results = run_bird(query, BIRD_SEARCH_MIN_COUNT, auth, ct0)
    return len(results) if results else 0


def find_earliest_year(phrase: str, auth: str, ct0: str) -> int:
    """Walk backward from current year to find earliest year with mentions."""
    current_year = today_utc().year
    earliest = current_year

    for year in range(current_year, X_LAUNCH_YEAR - 1, -1):
        print(f"  Checking {year}... ", end="", file=sys.stderr, flush=True)
        count = probe_range(phrase,
            f"since:{year}-01-01", f"until:{year + 1}-01-01", auth, ct0)
        print(f"({'✅' if count > 0 else '❌'}) ({count})", file=sys.stderr)
        if count > 0:
            earliest = year
        elif year < current_year:
            return year + 1

    return earliest


def find_earliest_month(phrase: str, year: int, auth: str, ct0: str) -> int:
    """Find the earliest month in a year where the phrase appears."""
    for month in range(1, 13):
        next_m = month + 1
        until_y, until_m = (year + 1, 1) if next_m > 12 else (year, next_m)
        print(f"  Checking {year}-{month:02d}... ", end="", file=sys.stderr, flush=True)
        count = probe_range(phrase,
            f"since:{year}-{month:02d}-01",
            f"until:{until_y}-{until_m:02d}-01", auth, ct0)
        print(f"({'✅' if count > 0 else '❌'}) ({count})", file=sys.stderr)
        if count > 0:
            return month
    return 1


def find_earliest_day(phrase: str, year: int, month: int,
                      auth: str, ct0: str) -> int:
    """Binary chop: find earliest day with mentions (single-day windows)."""
    if month == 12:
        days_in_month = 31
    else:
        next_m = datetime.date(year, month + 1, 1)
        days_in_month = (next_m - datetime.timedelta(days=1)).day

    lo, hi = 1, days_in_month
    first_day = days_in_month

    while lo <= hi:
        mid = (lo + hi) // 2
        print(f"  Checking {year}-{month:02d}-{mid:02d}... ", end="", file=sys.stderr, flush=True)

        day_end = mid + 1
        if day_end <= days_in_month:
            ck_y, ck_m, ck_d = year, month, day_end
        elif month == 12:
            ck_y, ck_m, ck_d = year + 1, 1, 1
        else:
            ck_y, ck_m, ck_d = year, month + 1, 1

        count = probe_range(phrase,
            f"since:{year}-{month:02d}-{mid:02d}",
            f"until:{ck_y}-{ck_m:02d}-{ck_d:02d}", auth, ct0)
        print(f"({'✅' if count > 0 else '❌'}) ({count})", file=sys.stderr)

        if count > 0:
            first_day = mid
            hi = mid - 1
        else:
            lo = mid + 1

    return first_day


def fetch_day_tweets(phrase: str, year: int, month: int, day: int,
                     auth: str, ct0: str) -> list:
    """Fetch tweets for a phrase on a specific day."""
    time.sleep(QUERY_DELAY)
    until_dt = datetime.date(year, month, day) + datetime.timedelta(days=1)
    query = (
        f'"{phrase}" '
        f"since:{year}-{month:02d}-{day:02d} "
        f"until:{until_dt.year}-{until_dt.month:02d}-{until_dt.day:02d}"
    )
    results = run_bird(query, BIRD_SEARCH_MAX_COUNT, auth, ct0)
    return results or []# ── Growth scan ───────────────────────────────────────────────────────

def build_windows(first_date: datetime.datetime) -> list:
    """Build time windows from first_date to today. Returns (label, since, until)."""
    today = today_utc()
    windows = []
    w1_end = first_date + datetime.timedelta(days=7)
    w2_end = first_date + datetime.timedelta(days=14)
    m1_end = first_date + datetime.timedelta(days=30)
    windows.append(("Week 1 (first 7 days)", first_date, min(w1_end, today)))
    windows.append(("Week 2", w1_end, min(w2_end, today)))
    windows.append(("Remainder of Month 1", w2_end, min(m1_end, today)))
    ws = m1_end
    month_num = 2
    while ws < today:
        we = min(ws + datetime.timedelta(days=30), today)
        windows.append((f"Month {month_num}", ws, we))
        ws = we
        month_num += 1
    return windows


def scan_growth(phrase: str, first_date: datetime.datetime,
                auth: str, ct0: str) -> list:
    """Scan mention frequency across growth windows."""
    windows = build_windows(first_date)
    results = []
    for label, since_dt, until_dt in windows:
        print(f"  {label}... ", end="", file=sys.stderr, flush=True)
        count = probe_range(phrase,
            f"since:{fmt_date(since_dt)}",
            f"until:{fmt_date(until_dt)}", auth, ct0)
        print(f"{count} posts", file=sys.stderr)
        results.append({"label": label, "since": fmt_date(since_dt),
                         "until": fmt_date(until_dt), "count": count})
    return results


# ── Output formatting ─────────────────────────────────────────────────

def format_og_post(tweet: dict) -> str:
    author = tweet.get("author", {})
    username = author.get("username", "?")
    name = author.get("name", "?")
    text = tweet.get("text", "")
    created = tweet.get("createdAt", "?")
    tid = tweet.get("id", "")
    likes = tweet.get("likeCount", 0)
    rts = tweet.get("retweetCount", 0)
    replies = tweet.get("replyCount", 0)
    views = tweet.get("viewCount", 0)
    return (
        f"\n"
        f"{'─' * 60}\n"
        f"  SEED POST FOUND\n"
        f"{'─' * 60}\n"
        f"\n"
        f"  Author:    @{username} ({name})\n"
        f"  Date:      {created}\n"
        f"  Link:      https://x.com/{username}/status/{tid}\n"
        f"\n"
        f"  {text}\n"
        f"\n"
        f"  ❤️ {likes}  ↻ {rts}  💬 {replies}  👁 {views}\n"
        f"\n"
        f"{'─' * 60}\n"
    )


def format_growth(windows: list) -> str:
    if not windows:
        return ""
    max_count = max(w["count"] for w in windows)
    bar_width = 40
    scale = bar_width / max_count if max_count > 0 else 1
    lines = ["", "─" * 60, "  GROWTH TIMELINE (mentions over time)",
             "─" * 60, ""]
    for w in windows:
        count = w["count"]
        bar_len = int(count * scale) if count > 0 else 0
        bar = "█" * min(bar_len, bar_width)
        lines.append(f"  {w['label']:27s} │ {count:3d}  {bar}")
    lines.append("")
    lines.append(f"  (bar width = {max_count} posts = {bar_width} chars)")
    lines.append("")
    return "\n".join(lines)


# ── Main pipeline ─────────────────────────────────────────────────────

def find_seed_post(phrase: str, auth: str, ct0: str,
                   growth: bool = False) -> dict:
    """Full pipeline. Returns result dict."""
    print(f"🔎 Searching for first mention of \"{phrase}\" on X", file=sys.stderr)

    print("Phase 1: Existence check", file=sys.stderr)
    count = probe_range(phrase,
        f"since:{X_LAUNCH_YEAR}-01-01",
        f"until:{today_utc().year + 1}-01-01", auth, ct0)
    if count == 0:
        print(f"\n  No mentions of \"{phrase}\" found.\n", file=sys.stderr)
        return {"found": False, "phrase": phrase}
    print(f"  ✅ Found — at least {count} result{'s' if count != 1 else ''}", file=sys.stderr)

    print("Phase 2: Binary-chop — earliest year", file=sys.stderr)
    year = find_earliest_year(phrase, auth, ct0)
    print(f"  → Earliest year: {year}", file=sys.stderr)

    print("Phase 3: Earliest month", file=sys.stderr)
    month = find_earliest_month(phrase, year, auth, ct0)
    print(f"  → Earliest month: {year}-{month:02d}", file=sys.stderr)

    print("Phase 4: Earliest day", file=sys.stderr)
    day = find_earliest_day(phrase, year, month, auth, ct0)
    print(f"  → Earliest day: {year}-{month:02d}-{day:02d}", file=sys.stderr)

    print("Phase 5: Finding the OG post", file=sys.stderr)
    tweets = fetch_day_tweets(phrase, year, month, day, auth, ct0)
    if not tweets:
        print("  No tweets returned for that day.", file=sys.stderr)
        return {"found": False, "phrase": phrase, "reason": "no_tweets_from_api"}

    exact = [t for t in tweets if exact_match(phrase, t)]
    exact.sort(key=lambda t: t.get("createdAt", ""))
    if not exact:
        print("  No exact substring matches (token-level only).", file=sys.stderr)
        return {"found": False, "phrase": phrase, "reason": "token_match_only"}

    first_tweet = exact[0]
    print(f"  ✅ @{first_tweet.get('author',{}).get('username','?')} — "
          f"{first_tweet.get('createdAt','?')}", file=sys.stderr)

    growth_data = None
    if growth:
        print(file=sys.stderr)
        print("Phase 6: Growth scan", file=sys.stderr)
        first_date = parse_timestamp(first_tweet["createdAt"])
        growth_data = scan_growth(phrase, first_date, auth, ct0)

    return {"found": True, "phrase": phrase, "og_post": first_tweet,
            "growth": growth_data}


def main():
    parser = argparse.ArgumentParser(
        description="Find the first mention of a phrase on X/Twitter")
    parser.add_argument("phrase", help="The exact phrase to search for")
    parser.add_argument("--graph", "-g", action="store_true",
                        help="Run growth scan (mention frequency over time windows)")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output results as JSON (machine-readable)")
    parser.add_argument("--install", action="store_true",
                        help="Install @steipete/bird dependency if missing")

    args = parser.parse_args()
    phrase = args.phrase.strip()

    if len(phrase) < 2:
        print("error: phrase must be at least 2 characters", file=sys.stderr)
        sys.exit(1)

    # Install check
    if not bird_is_installed():
        if args.install:
            if not install_bird():
                sys.exit(1)
        else:
            print(
                f"\n  @steipete/bird (npm CLI) is required but not installed.\n"
                f"  Run:  cd {PROJECT_DIR} && npm install\n"
                f"  Or:   python seed-post.py --install \"{phrase}\"\n",
                file=sys.stderr,
            )
            sys.exit(1)

    # Run
    auth, ct0 = load_credentials()
    result = find_seed_post(phrase, auth, ct0, growth=args.graph)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    elif result.get("found"):
        print(format_og_post(result["og_post"]))
        if result.get("growth"):
            print(format_growth(result["growth"]))
    else:
        print(f"\n  No seed post found for \"{args.phrase}\".\n")


if __name__ == "__main__":
    main()