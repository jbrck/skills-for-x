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

def is_compound_query(phrase: str) -> bool:
    """Check if phrase contains search operators that break exact-phrase wrapping."""
    operators = {'"', 'OR', 'AND', '-', 'from:', 'to:', 'url:', 'lang:', 'has:'}
    return any(op in phrase for op in operators)


def probe_range(phrase: str, since_str: str, until_str: str,
                auth: str, ct0: str) -> int:
    """Return VALIDATED result count for phrase in a date range.

    0 = none/error. The GraphQL search falls back to random in-window
    popular tweets when no real match exists in the range, so raw
    len(results) is NOT a reliable signal. Every result is checked:
      - date falls within the queried window (with 24h TZ slack on each
        side — bird interprets since/until in the browser's timezone)
      - text matches the phrase, when the query is a plain phrase
    Only validated results count.
    """
    time.sleep(QUERY_DELAY)
    query = (f'"{phrase}"' if not is_compound_query(phrase) else phrase) + f' {since_str} {until_str}'
    results = run_bird(query, BIRD_SEARCH_MIN_COUNT, auth, ct0)
    if not results:
        return 0

    # Parse the requested window (YYYY-MM-DD) and add TZ slack
    since_parts = since_str.removeprefix("since:").split("-")
    until_parts = until_str.removeprefix("until:").split("-")
    win_lo = datetime.datetime(int(since_parts[0]), int(since_parts[1]), int(since_parts[2]),
                               tzinfo=datetime.timezone.utc)
    win_hi = datetime.datetime(int(until_parts[0]), int(until_parts[1]), int(until_parts[2]),
                               tzinfo=datetime.timezone.utc)
    slack = datetime.timedelta(hours=24)
    check_phrase = not is_compound_query(phrase) and len(phrase) >= 2

    count = 0
    for t in results:
        try:
            created = parse_timestamp(t.get("createdAt", ""))
        except (ValueError, IndexError, KeyError):
            continue
        if not (win_lo - slack <= created <= win_hi + slack):
            continue
        if check_phrase and not exact_match(phrase, t):
            continue
        count += 1
    return count


def find_earliest_year(phrase: str, auth: str, ct0: str,
                       start_year: int = X_LAUNCH_YEAR,
                       end_year: int | None = None) -> tuple | None:
    """Sweep 6-month windows to find the earliest year with matches.

    bird's GraphQL search ranks by relevance+popularity INSIDE the
    window. For windows wider than ~6 months, real but rare old matches
    fall out of the top-N and the probe falsely returns 0 (verified: a
    2009-01→2010-01 probe returns 0 for 'bitcoin' even though Jan 2009
    has real hits; the same probe on 2009-01→2009-07 returns them).
    Bi-directional chopping does NOT help — it's the API, not direction.

    So the reliable primitive is a narrow-window sweep: probe consecutive
    6-month windows from the start year, return the first window with a
    validated hit. Then month/day chops run inside that ~6-month window,
    where narrow probes are dependable.

    Returns (year, month) of the first hit window, or None.
    """
    if end_year is None:
        end_year = today_utc().year

    # Walk H1/H2 windows from start_year forward
    win_start_y, win_start_m = start_year, 1
    while win_start_y < end_year or (win_start_y == end_year and win_start_m == 1):
        # window end: start + 6 months
        win_end_y, win_end_m = win_start_y, win_start_m + 6
        if win_end_m > 12:
            win_end_y += 1
            win_end_m -= 12
        # clamp to the requested end_year
        if win_end_y > end_year:
            win_end_y, win_end_m = end_year + 1, 1
        if win_start_y > end_year:
            break
        win_last = datetime.date(win_end_y, win_end_m, 1) - datetime.timedelta(days=1)
        label = f"{win_start_y}-{win_start_m:02d}..{win_last.year}-{win_last.month:02d}"
        print(f"  Sweep {label}... ", end="", file=sys.stderr, flush=True)
        count = probe_range(phrase,
            f"since:{win_start_y}-{win_start_m:02d}-01",
            f"until:{win_end_y}-{win_end_m:02d}-01", auth, ct0)
        print(f"({'✅' if count > 0 else '❌'}) ({count})", file=sys.stderr)
        if count > 0:
            print(f"  ✓ First hit window: {label}", file=sys.stderr)
            return win_start_y, win_start_m
        # advance by 6 months
        win_start_m += 6
        if win_start_m > 12:
            win_start_y += 1
            win_start_m -= 12
    return None



def find_earliest_month_window(phrase: str, start_ym: tuple, auth: str, ct0: str) -> tuple:
    """Find the earliest (year, month) inside the hit window.

    Binary chop over the flat month list between start_ym and +5 months.
    The window is ≤6 months wide, so every probe is narrow and reliable.
    """
    y0, m0 = start_ym
    # Candidate months: [start .. start+5]
    months = []
    y, m = y0, m0
    for _ in range(6):
        months.append((y, m))
        m += 1
        if m > 12:
            y += 1
            m = 1

    lo, hi = 0, len(months) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        y_lo, m_lo = months[lo]
        y_mid, m_mid = months[mid]
        next_m = mid + 1
        y_hi, m_hi = months[next_m] if next_m < len(months) else (y_mid, m_mid + 1)
        if m_hi > 12:
            y_hi, m_hi = y_mid + 1, 1
        print(f"  Checking {y_lo}-{m_lo:02d}..{y_mid}-{m_mid:02d}... ",
              end="", file=sys.stderr, flush=True)
        left = probe_range(phrase,
            f"since:{y_lo}-{m_lo:02d}-01", f"until:{y_hi}-{m_hi:02d}-01",
            auth, ct0)
        print(f"({'✅' if left > 0 else '❌'}) ({left})", file=sys.stderr)
        if left > 0:
            hi = mid
        else:
            lo = mid + 1
    return months[lo]


def find_earliest_month(phrase: str, year: int, auth: str, ct0: str) -> int:
    """Find the earliest month in a year where the phrase appears.

    Existence-based binary chop over months: probe the [lo, mid] half;
    if hits, recurse left, else fork right. ~4 probes instead of 12.
    """
    lo, hi = 1, 12
    while lo < hi:
        mid = (lo + hi) // 2
        next_m = mid + 1
        until_y, until_m = (year + 1, 1) if next_m > 12 else (year, next_m)
        print(f"  Checking {year}-{lo:02d}..{mid:02d}... ", end="", file=sys.stderr, flush=True)
        left = probe_range(phrase,
            f"since:{year}-{lo:02d}-01", f"until:{until_y}-{until_m:02d}-01",
            auth, ct0)
        print(f"({'✅' if left > 0 else '❌'}) ({left})", file=sys.stderr)
        if left > 0:
            hi = mid
        else:
            lo = mid + 1
    return lo


def find_earliest_day(phrase: str, year: int, month: int,
                      auth: str, ct0: str) -> int:
    """Find earliest day with mentions via existence-based binary chop.
    Month has at most 31 days — a chop takes ~5 probes instead of 31,
    which matters because every probe pays the 2.5s API delay.
    """
    if month == 12:
        days_in_month = 31
    else:
        next_m = datetime.date(year, month + 1, 1)
        days_in_month = (next_m - datetime.timedelta(days=1)).day

    def range_end(day: int) -> tuple:
        """(y, m, d) of the day after `day` in the same month/year."""
        if day < days_in_month:
            return year, month, day + 1
        if month == 12:
            return year + 1, 1, 1
        return year, month + 1, 1

    print(f"  Chopping {year}-{month:02d} day range...", file=sys.stderr, flush=True)
    lo, hi = 1, days_in_month
    while lo < hi:
        mid = (lo + hi) // 2
        ey, em, ed = range_end(mid)
        print(f"  Checking day {lo:02d}..{mid:02d}... ", end="", file=sys.stderr, flush=True)
        left = probe_range(phrase,
            f"since:{year}-{month:02d}-{lo:02d}", f"until:{ey}-{em:02d}-{ed:02d}",
            auth, ct0)
        print(f"({'✅' if left > 0 else '❌'}) ({left})", file=sys.stderr)
        if left > 0:
            hi = mid
        else:
            lo = mid + 1

    print(f"  > Earliest day: {year}-{month:02d}-{lo:02d}", file=sys.stderr)
    return lo


def fetch_day_tweets(phrase: str, year: int, month: int, day: int,
                     auth: str, ct0: str) -> list:
    """Fetch tweets for a phrase on the resolved day.

    Mirrors probe semantics: bird interprets since/until in the user's
    browser timezone (≈UTC-8), so a tweet from Jan 11 03:33 UTC lands in
    an until:Jan-10 window. A strict UTC filter therefore DROPS the very
    tweet we want. Instead we accept whatever the windowed query returns,
    exact-match it, and sort chronologically — the earliest is the OG.

    Uses count=3 (probe count) + a count=60 sweep for older same-window
    posts, then keeps posts whose createdAt is within ~2 days of the
    resolved day (TZ slack) and exact-matches the phrase.
    """
    time.sleep(QUERY_DELAY)
    window = f"since:{year}-{month:02d}-{day:02d} " \
             f"until:{fmt_date(datetime.date(year, month, day) + datetime.timedelta(days=1))}"
    prefix = f'"{phrase}"' if not is_compound_query(phrase) else phrase

    results: list = []
    for count in (BIRD_SEARCH_MIN_COUNT, BIRD_SEARCH_MAX_COUNT):
        page = run_bird(f"{prefix} {window}", count, auth, ct0)
        if page:
            results.extend(page)

    # TZ-lenient window: resolved day minus 48h to plus 48h.
    resolved = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
    slack_lo = resolved - datetime.timedelta(hours=48)
    slack_hi = resolved + datetime.timedelta(hours=168)

    seen = set()
    kept = []
    for t in results:
        tid = t.get("id")
        if tid and tid in seen:
            continue
        if tid:
            seen.add(tid)
        try:
            created = parse_timestamp(t.get("createdAt", ""))
        except (ValueError, IndexError, KeyError):
            continue
        if slack_lo <= created <= slack_hi and exact_match(phrase, t):
            kept.append(t)
    kept.sort(key=lambda t: t.get("createdAt", ""))
    return kept


# ── Growth scan ───────────────────────────────────────────────────────

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
        prefix = f'"{phrase}"' if not is_compound_query(phrase) else phrase
        query = f'{prefix} since:{fmt_date(since_dt)} until:{fmt_date(until_dt)}'
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
    
    # Wrap text to ~50 chars
    words = text.split()
    wrapped = []
    line = ""
    for w in words:
        if len(line) + len(w) + 1 > 50:
            wrapped.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        wrapped.append(line)
    
    card = []
    card.append("╔══════════════════════════════════════════════════════╗")
    card.append("║  SEED POST FOUND                                    ║")
    card.append("╠══════════════════════════════════════════════════════╣")
    card.append(f"║  @{username:<46s} ║")
    card.append(f"║  {created:<46s} ║")
    card.append(f"║  https://x.com/{username}/status/{tid:<12s}║")
    card.append("╠══════════════════════════════════════════════════════╣")
    for line in wrapped:
        card.append(f"║  {line:<48s} ║")
    card.append("╠══════════════════════════════════════════════════════╣")
    card.append(f"║  ❤️ {likes:<5d}  ↻ {rts:<5d}  💬 {replies:<5d}  👁 {views:<5d}    ║")
    card.append("╚══════════════════════════════════════════════════════╝")
    return "\n".join(card)


def format_growth(windows: list) -> str:
    """Format growth data as a compact card-style table.

    Collapses consecutive windows with the same count into a single
    "YYYY+" row for readability (mostly affects annual scans on
    popular terms where the API sample cap is reached).
    """
    if not windows:
        return ""

    max_count = max(w["count"] for w in windows)
    bar_width = 30
    scale = bar_width / max_count if max_count > 0 else 1
    
    lines = ["╔══════════════════════════════════════════════════════╗",
             "║  GROWTH TIMELINE     mentions over time              ║",
             "╠════╦══════════════════╦═══════╦═══════════════════════╣"]

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
        lbl = d["label"]
        dr = d.get("date_range", "")
        lines.append(f"║ {lbl:>5s} ║ {dr:28s} ║ {count:5d} ║ {bar:{bar_width}s} ║")

    collapsed_total = sum(d.get("collapsed", 0) for d in display if d.get("collapsed"))
    if collapsed_total:
        last_count = display[-1]["count"] if display else 0
        collapsed_rows = sum(1 for d in display if d.get("collapsed"))
        lines.append(f"╠════╧══════════════════╧═══════╧═══════════════════╣")
        lines.append(f"║ {collapsed_total}yrs @ {last_count}+ posts — {collapsed_rows} row{'s' if collapsed_rows>1 else ''}  ║")

    lines.append(f"╚══════════════════════════════════════════════════════╝")
    return "\n".join(lines)


def fetch_early_shares(tweet_id: str, tweet_created_at: str,
                       phrase: str, auth: str, ct0: str,
                       max_shares: int = 5) -> list:
    """Fetch the first posts that mentioned the phrase after the seed post.

    Searches for the phrase in a 7-day window after the OG post and
    excludes the seed post itself. Captures early retweets, quote tweets,
    and independent mentions — anyone who picked up the term next.
    """
    seed_dt = parse_timestamp(tweet_created_at)
    day_after = seed_dt + datetime.timedelta(days=1)
    week_later = seed_dt + datetime.timedelta(days=7)

    time.sleep(QUERY_DELAY)
    prefix = f'"{phrase}" ' if not is_compound_query(phrase) else f'{phrase} '
    query = (
        f"{prefix}since:{fmt_date(day_after)} "
        f"until:{fmt_date(week_later)}"
    )
    results = run_bird(query, 30, auth, ct0)
    if not results:
        return []

    # Filter to posts with the phrase, exclude the seed post itself
    early = []
    seen_ids = {tweet_id}
    for t in results:
        if t.get("id") and t["id"] not in seen_ids and exact_match(phrase, t):
            early.append(t)
            seen_ids.add(t["id"])
        if len(early) >= max_shares:
            break
    return early


def format_early_shares(shares: list) -> str:
    """Format early shares as a compact card."""
    if not shares:
        return ""
    card = []
    card.append("╔══════════════════════════════════════════════════════╗")
    card.append("║  EARLY MENTIONS   who picked it up next                ║")
    card.append("╠══════════════════════════════════════════════════════╣")
    for i, t in enumerate(shares, 1):
        author = t.get("author", {})
        username = author.get("username", "?")
        text = t.get("text", "").replace("\n", " ")[:80]
        created = t.get("createdAt", "?")
        card.append(f"║  {i}. @{username:<35s}           ║")
        card.append(f"║     {created:<44s} ║")
        # Wrap text
        words = text.split()
        line = ""
        for w in words:
            if len(line) + len(w) + 1 > 44:
                card.append(f"║     {line:<44s} ║")
                line = w
            else:
                line = (line + " " + w).strip()
        if line:
            card.append(f"║     {line:<44s} ║")
        if i < len(shares):
            card.append("╠══════════════════════════════════════════════════════╣")
    card.append("╚══════════════════════════════════════════════════════╝")
    return "\n".join(card)


def format_candidates(candidates: list) -> str:
    """Format displaced runner-up candidates as a compact card."""
    if not candidates:
        return ""
    card = []
    card.append("╔══════════════════════════════════════════════════════╗")
    card.append("║  DISPLACED CANDIDATES  found during the chop          ║")
    card.append("╠══════════════════════════════════════════════════════╣")
    for i, t in enumerate(candidates, 1):
        author = t.get("author", {})
        username = author.get("username", "?")
        text = t.get("text", "").replace("\n", " ")[:80]
        created = t.get("createdAt", "?")
        card.append(f"║  {i}. @{username:<35s}           ║")
        card.append(f"║     {created:<44s} ║")
        words = text.split()
        line = ""
        for w in words:
            if len(line) + len(w) + 1 > 44:
                card.append(f"║     {line:<44s} ║")
                line = w
            else:
                line = (line + " " + w).strip()
        if line:
            card.append(f"║     {line:<44s} ║")
        if i < len(candidates):
            card.append("╠══════════════════════════════════════════════════════╣")
    card.append("╚══════════════════════════════════════════════════════╝")
    return "\n".join(card)


# ── Main pipeline ─────────────────────────────────────────────────────

def find_seed_post(phrase: str, auth: str, ct0: str,
                   growth: bool = False,
                   after_date: str | None = None,
                   before_date: str | None = None,
                   window_days: int | None = None,
                   annual: bool = False,
                   shares_count: int = 0,
                   candidates_count: int = 0) -> dict:
    """Full pipeline. Returns result dict.

    Supports --after, --before bounds and --window/--annual for growth.
    When shares_count > 0, also fetches early mentions after the seed post.
    When candidates_count > 0, logs runner-up candidates found during the
    final day fetch — posts the OG post displaced on the first day(s).
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

    print("Phase 1+2: Semester sweep — existence + earliest window", file=sys.stderr)
    hit = find_earliest_year(phrase, auth, ct0,
                             start_year=start_year, end_year=end_year)
    if hit is None:
        print(f"\n  No mentions of \"{phrase}\" found in that range.\n", file=sys.stderr)
        return {"found": False, "phrase": phrase}
    year, month = hit
    print(f"  → Earliest window starts: {year}-{month:02d}", file=sys.stderr)

    print("Phase 3: Earliest month", file=sys.stderr)
    year, month = find_earliest_month_window(phrase, (year, month), auth, ct0)
    print(f"  → Earliest month: {year}-{month:02d}", file=sys.stderr)

    print("Phase 4: Earliest day", file=sys.stderr)
    day = find_earliest_day(phrase, year, month, auth, ct0)
    print(f"  → Earliest day: {year}-{month:02d}-{day:02d}", file=sys.stderr)

    print("Phase 5: Finding the OG post", file=sys.stderr)
    # The day chop can land on a false positive: the API sometimes returns
    # an out-of-window relevance post for a since/until probe (count > 0,
    # but no post actually lives on that day). Verify with a real fetch;
    # if the day is empty, walk forward up to 120 days until the fetch
    # returns in-window posts.
    cur = datetime.date(year, month, day)
    tweets = []
    walk_days = 0
    while walk_days <= 120:
        print(f"  DEBUG: fetch_day_tweets({phrase!r}, y={cur.year}, m={cur.month}, d={cur.day})",
              file=sys.stderr)
        tweets = fetch_day_tweets(phrase, cur.year, cur.month, cur.day, auth, ct0)
        print(f"  DEBUG: got {len(tweets)} tweets for {cur.isoformat()}", file=sys.stderr)
        if tweets:
            break
        cur = cur + datetime.timedelta(days=1)
        walk_days += 1

    if tweets:
        for t in tweets[:2]:
            print(f"  DEBUG: @{t.get('author',{}).get('username','?')} ({t.get('createdAt','?')}): {t.get('text','')[:80]}",
                  file=sys.stderr)
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

    candidates_data = None
    if candidates_count > 0 and len(exact) > 1:
        # The OG post displaced these — they're the runner-ups found
        # during the same final fetch. No extra API calls.
        candidates_data = exact[1:candidates_count + 1]
        print(f"  → Kept {len(candidates_data)} displaced candidate"
              f"{'s' if len(candidates_data) != 1 else ''} (from first fetch)",
              file=sys.stderr)

    growth_data = None
    if growth:
        print(file=sys.stderr)
        print("Phase 6: Growth scan", file=sys.stderr)
        first_date = parse_timestamp(first_tweet["createdAt"])
        growth_data = scan_growth(phrase, first_date, auth, ct0,
                                  window_days=window_days,
                                  annual=annual)

    shares_data = None
    if shares_count > 0:
        print(file=sys.stderr)
        print(f"Phase 7: Early mentions (first {shares_count})", file=sys.stderr)
        shares_data = fetch_early_shares(
            first_tweet["id"], first_tweet["createdAt"],
            phrase, auth, ct0, max_shares=shares_count)
        print(f"  → Found {len(shares_data)} early mention{'s' if len(shares_data)!=1 else ''}",
              file=sys.stderr)

    return {"found": True, "phrase": phrase, "og_post": first_tweet,
            "growth": growth_data, "early_shares": shares_data,
            "candidates": candidates_data}


OPTIONS_TEXT = """\
seed-post — find the first mention of any phrase on X/Twitter.

Usage:
  python3 seed-post.py <phrase> [options]

Examples:
  python3 seed-post.py "bitcoin"
  python3 seed-post.py "bitcoin" --graph
  python3 seed-post.py "bitcoin" --shares 5
  python3 seed-post.py "bitcoin" --candidates 5
  python3 seed-post.py "bitcoin" --after 2010-01-01 --before 2010-12-31

Options:
  --graph, -g       Show growth timeline (mentions over time)
  --shares N        Show first N early mentions after the seed post
  --candidates N    Log N displaced runner-up candidates found during the chop
  --after DATE      Only search after this date (YYYY-MM-DD)
  --before DATE     Only search before this date (YYYY-MM-DD)
  --window DUR      Growth window size: '7d', '30d', '3m', '1y'
  --annual          Annual growth windows (calendar years)
  --json, -j        Output raw JSON (machine-readable)
  --install         Install @steipete/bird dependency if missing
  --help, -h        Show this help

Run interactively with no flags and the tool will ask about a time window.
"""


def prompt_time_window() -> tuple[str | None, str | None]:
    """Ask the user if they know a time window to search within.

    Returns (after, before) — either may be None, which means
    'no bound' for the full-archive scan. Interactive only.
    """
    print(file=sys.stderr)
    print("Do you know roughly when the term first appeared?", file=sys.stderr)
    print("  [1] No idea — scan the full archive (2006 to today)", file=sys.stderr)
    print("  [2] It was in a specific year (e.g. 2010)", file=sys.stderr)
    print("  [3] It was between two dates (e.g. 2008-03 to 2010-07)", file=sys.stderr)
    print("  Enter 1-3 (default 1): ", end="", file=sys.stderr, flush=True)
    choice = input().strip()

    if choice == "2":
        print("  Which year? (YYYY): ", end="", file=sys.stderr, flush=True)
        yr = input().strip()
        if re.match(r"^\d{4}$", yr):
            return f"{yr}-01-01", f"{yr}-12-31"
        print(f"  Invalid year '{yr}' — scanning full archive.", file=sys.stderr)
        return None, None

    if choice == "3":
        print("  Start date (YYYY-MM-DD): ", end="", file=sys.stderr, flush=True)
        after = input().strip()
        print("  End date (YYYY-MM-DD): ", end="", file=sys.stderr, flush=True)
        before = input().strip()
        ok_after = bool(re.match(r"^\d{4}-\d{2}-\d{2}$", after)) if after else False
        ok_before = bool(re.match(r"^\d{4}-\d{2}-\d{2}$", before)) if before else False
        if ok_after and ok_before:
            return after, before
        if ok_after and not before:
            return after, None
        if ok_before and not after:
            return None, before
        print("  Invalid date format — scanning full archive.", file=sys.stderr)
        return None, None

    # choice 1 or anything unparseable → full archive
    return None, None


def main():
    parser = argparse.ArgumentParser(
        description="Find the first mention of a phrase on X/Twitter",
        add_help=True)
    parser.add_argument("phrase", nargs="?", help="The exact phrase to search for")
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
    parser.add_argument("--shares", type=int, default=0, metavar="N",
                        help="Show first N early mentions after the seed post (default: off)")
    parser.add_argument("--candidates", type=int, default=0, metavar="N",
                        help="Log up to N displaced runner-up candidates found during the chop (default: off)")

    args = parser.parse_args()

    # No phrase → print friendly options and exit 0.
    if not args.phrase:
        print(OPTIONS_TEXT)
        sys.exit(0)

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

    # If neither bound is set, ask if the user knows a time window.
    # Interactive only — piping/CI skips the prompt and scans the full archive.
    if not args.after and not args.before and sys.stdin.isatty():
        args.after, args.before = prompt_time_window()

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
                            annual=args.annual,
                            shares_count=args.shares,
                            candidates_count=args.candidates)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    elif result.get("found"):
        print(format_og_post(result["og_post"]))
        if result.get("candidates"):
            print(format_candidates(result["candidates"]))
        if result.get("early_shares"):
            print(format_early_shares(result["early_shares"]))
        if result.get("growth"):
            print(format_growth(result["growth"]))
    else:
        print(f"\n  No seed post found for \"{args.phrase}\".\n")


if __name__ == "__main__":
    main()