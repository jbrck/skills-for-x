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
import re
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
    """Run @steipete/bird search. Returns list of tweet dicts or empty list.
    Retries on rate limits (429) with exponential backoff.
    """
    cmd = [
        str(BIRD_BIN), "--auth-token", auth, "--ct0", ct0,
        "search", query,
        "--count", str(count), "--json",
    ]
    for attempt in range(3):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            print("  [timeout]", file=sys.stderr)
            return []

        if result.returncode == 0 and result.stdout.strip():
            try:
                tweets = json.loads(result.stdout)
                return tweets if isinstance(tweets, list) else []
            except json.JSONDecodeError:
                return []

        # Check for rate limit
        err = result.stderr.strip()[:200]
        if err and "429" in err:
            wait = 2 ** attempt * 20  # 20s, 40s, 80s
            print(f"  [rate limited — retrying in {wait}s]", file=sys.stderr)
            time.sleep(wait)
            continue

        # Non-rate-limit error — don't retry
        if err:
            print(f"  [{err}]", file=sys.stderr)
        return []

    print("  [gave up after 3 retries]", file=sys.stderr)
    return []


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


def parse_window_duration(dur_str: str) -> int | None:
    """Parse duration like '30d', '3m', '1y' into days. Returns None if unparseable."""
    m = re.match(r"^(\d+)([dmy])$", dur_str.strip().lower())
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2)
    if unit == "d":
        return val
    elif unit == "m":
        return val * 30
    elif unit == "y":
        return val * 365


def parse_ymd(date_str: str) -> tuple:
    """Parse YYYY-MM-DD into (year, month, day)."""
    parts = date_str.split("-")
    return int(parts[0]), int(parts[1]), int(parts[2])


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


def find_earliest_year(phrase: str, auth: str, ct0: str,
                       start_year: int = X_LAUNCH_YEAR,
                       end_year: int | None = None) -> int:
    """Walk backward from end_year to start_year to find earliest year."""
    if end_year is None:
        end_year = today_utc().year
    earliest = end_year

    for year in range(end_year, start_year - 1, -1):
        print(f"  Checking {year}... ", end="", file=sys.stderr, flush=True)
        count = probe_range(phrase,
            f"since:{year}-01-01", f"until:{year + 1}-01-01", auth, ct0)
        print(f"({'✅' if count > 0 else '❌'}) ({count})", file=sys.stderr)
        if count > 0:
            earliest = year
        elif year < end_year:
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
    """Find earliest day with mentions via linear scan.
    Month has at most 31 days — linear scan is reliable and fast enough.
    """
    if month == 12:
        days_in_month = 31
    else:
        next_m = datetime.date(year, month + 1, 1)
        days_in_month = (next_m - datetime.timedelta(days=1)).day

    print(f"  Scanning {year}-{month:02d} day by day...", file=sys.stderr, flush=True)
    for day in range(1, days_in_month + 1):
        day_end = day + 1
        if day_end <= days_in_month:
            ck_y, ck_m, ck_d = year, month, day_end
        elif month == 12:
            ck_y, ck_m, ck_d = year + 1, 1, 1
        else:
            ck_y, ck_m, ck_d = year, month + 1, 1

        count = probe_range(phrase,
            f"since:{year}-{month:02d}-{day:02d}",
            f"until:{ck_y}-{ck_m:02d}-{ck_d:02d}", auth, ct0)
        if count > 0:
            print(f"  > Earliest day: {year}-{month:02d}-{day:02d}",
                  file=sys.stderr)
            return day

    return days_in_month  # fallback


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

def build_windows(first_date: datetime.datetime,
                  window_days: int | None = None,
                  annual: bool = False) -> list:
    """Build time windows from first_date to today.
    Returns list of (label, since_dt, until_dt).

    When annual=True, uses calendar-year windows from first_date's year to today.
    When window_days is set, uses repeated windows of that duration.
    Otherwise uses default scheme (week 1, week 2, remainder, month 2, month 3).
    """
    first_dt = first_date.date()
    today = today_utc()

    if annual:
        windows = []
        now_year = today.year
        for year in range(first_dt.year, now_year + 1):
            jan1 = datetime.date(year, 1, 1)
            dec31 = datetime.date(year, 12, 31)
            since = first_dt if year == first_dt.year else jan1
            until = today.date() if year == now_year else dec31
            windows.append((str(year), since, until))
        return windows

    if window_days is not None:
        windows = []
        cur = first_dt
        idx = 1
        t = today.date()
        while cur < t:
            nxt = cur + datetime.timedelta(days=window_days)
            if nxt > t:
                nxt = t
            windows.append((f"Window {idx}", cur, nxt))
            cur = nxt
            idx += 1
        return windows

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
def fmt_date_range(since: str, until: str) -> str:
    """Format date range for display.
    Same month: 'Sep 22-29'
    Different month: 'Sep 22 - Oct 19'
    Different year: 'Dec 22 2026 - Jan 19 2027'
    """
    since_parts = since.split("-")
    until_parts = until.split("-")
    months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    sm, sd = int(since_parts[1]), int(since_parts[2])
    um, ud = int(until_parts[1]), int(until_parts[2])
    if since_parts[0] == until_parts[0] and sm == um:
        return f"{months[sm]} {sd}-{ud}"
    elif since_parts[0] == until_parts[0]:
        return f"{months[sm]} {sd} - {months[um]} {ud}"
    else:
        return f"{months[sm]} {sd} {since_parts[0]} - {months[um]} {ud}"


def scan_growth(phrase: str, first_date: datetime.datetime,
                auth: str, ct0: str,
                window_days: int | None = None,
                annual: bool = False) -> list:
    """Scan mention frequency across growth windows."""
    GScan = 100  # ask for more for growth scan cuz we need actual counts
    windows = build_windows(first_date, window_days=window_days,
                            annual=annual)
    results = []
    for label, since_dt, until_dt in windows:
        print(f"  {label}... ", end="", file=sys.stderr, flush=True)
        query = f'"{phrase}" since:{fmt_date(since_dt)} until:{fmt_date(until_dt)}'
        tweets = run_bird(query, GScan, auth, ct0)
        count = len(tweets)
        print(f"{count} posts", file=sys.stderr)
        results.append({"label": label, "since": fmt_date(since_dt),
                         "until": fmt_date(until_dt), "count": count,
                         "date_range": fmt_date_range(fmt_date(since_dt),
                                                       fmt_date(until_dt))})
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
    """Format growth data as a table with header, bars and counts.

    Collapses consecutive windows with the same count into a single
    "YYYY+" row for readability (mostly affects annual scans on
    popular terms where the API sample cap is reached).
    """
    if not windows:
        return ""

    max_count = max(w["count"] for w in windows)
    bar_width = 40
    scale = bar_width / max_count if max_count > 0 else 1
    lines = ["", "─" * 60, "  GROWTH TIMELINE (mentions over time)",
             "─" * 60, "",
             "  Year   Date Range                 Count",
             "  " + "─" * 52, ""]

    # Collapse runs of 3+ consecutive windows with the same count
    display = []
    i = 0
    while i < len(windows):
        w = windows[i]
        count = w["count"]
        run = 1
        while i + run < len(windows) and windows[i + run]["count"] == count:
            run += 1
        if run >= 3:
            first = windows[i]
            last = windows[i + run - 1]
            collapsed = f"{first['label']}+"
            dr = first.get("date_range", "").split(" - ")[0].split(" ")[-1] + " onward"
            display.append({"label": collapsed, "count": count,
                            "date_range": dr, "collapsed": run})
            i += run
        else:
            display.append(w)
            i += 1

    for d in display:
        count = d["count"]
        bar_len = int(count * scale) if count > 0 else 0
        bar = "█" * min(bar_len, bar_width)
        dr = d.get("date_range", "")
        lines.append(f"  {d['label']:5s}  {dr:30s}  {count:5d}  {bar}")

    collapsed_total = sum(d.get("collapsed", 0) for d in display if d.get("collapsed"))
    if collapsed_total:
        lines.append("")
        last_count = display[-1]["count"] if display else 0
        lines.append(f"  ({collapsed_total} years with {last_count}+ posts collapsed into "
                     f"{sum(1 for d in display if d.get('collapsed'))} rows — "
                     "API sample cap reached)")

    lines.append("")
    lines.append(f"  (bar width = {max_count} posts = {bar_width} chars)")
    lines.append("")
    return "\n".join(lines)


# ── Main pipeline ─────────────────────────────────────────────────────

def find_seed_post(phrase: str, auth: str, ct0: str,
                   growth: bool = False,
                   after_date: str | None = None,
                   before_date: str | None = None,
                   window_days: int | None = None,
                   annual: bool = False) -> dict:
    """Full pipeline. Returns result dict.

    Supports --after, --before bounds and --window/--annual for growth.
    """
    print(f"🔎 Searching for first mention of \"{phrase}\" on X", file=sys.stderr)

    # Resolve search bounds from --after/--before
    start_year = X_LAUNCH_YEAR
    end_year = today_utc().year
    if after_date:
        sy, sm, sd = parse_ymd(after_date)
        start_year = sy
    if before_date:
        ey, em, ed = parse_ymd(before_date)
        end_year = ey

    lo = after_date or f"{start_year}-01-01"
    hi = before_date or f"{end_year}-12-31"
    print(f"  Range: {lo} → {hi}", file=sys.stderr)

    print("Phase 1: Existence check", file=sys.stderr)
    since = f"since:{after_date}" if after_date else f"since:{start_year}-01-01"
    until = f"until:{int(end_year) + 1}-01-01" if not before_date else f"until:{before_date}"
    count = probe_range(phrase, since, until, auth, ct0)
    if count == 0:
        print(f"\n  No mentions of \"{phrase}\" found in that range.\n", file=sys.stderr)
        return {"found": False, "phrase": phrase}
    print(f"  ✅ Found — at least {count} result{'s' if count != 1 else ''}", file=sys.stderr)

    print("Phase 2: Binary-chop — earliest year", file=sys.stderr)
    year = find_earliest_year(phrase, auth, ct0, start_year=start_year, end_year=end_year)
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
        growth_data = scan_growth(phrase, first_date, auth, ct0,
                                  window_days=window_days,
                                  annual=annual)

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
    parser.add_argument("--after", metavar="YYYY-MM-DD",
                        help="Only search after this date (inclusive)")
    parser.add_argument("--before", metavar="YYYY-MM-DD",
                        help="Only search before this date (exclusive)")
    parser.add_argument("--window", metavar="DURATION",
                        help="Growth window duration: '7d', '30d', '3m', '1y' etc.")
    parser.add_argument("--annual", action="store_true",
                        help="Annual growth windows (calendar years from OG post)")

    args = parser.parse_args()
    phrase = args.phrase.strip()

    if len(phrase) < 2:
        print("error: phrase must be at least 2 characters", file=sys.stderr)
        sys.exit(1)

    # Validate --after/--before format
    for flag in ["after", "before"]:
        val = getattr(args, flag)
        if val and not re.match(r"^\d{4}-\d{2}-\d{2}$", val):
            print(f"error: --{flag} must be YYYY-MM-DD format, got '{val}'",
                  file=sys.stderr)
            sys.exit(1)

    # Parse --window
    window_days = None
    if args.window:
        window_days = parse_window_duration(args.window)
        if window_days is None:
            print(f"error: --window must be like '30d', '3m', or '1y', got '{args.window}'",
                  file=sys.stderr)
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
    result = find_seed_post(phrase, auth, ct0, growth=args.graph,
                            after_date=args.after, before_date=args.before,
                            window_days=window_days,
                            annual=args.annual)

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