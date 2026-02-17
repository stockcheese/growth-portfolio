#!/usr/bin/env python3
"""
update_prices.py — Fetch live stock data via yfinance and update index.html

Uses regex-based replacement to update only data-attributed elements.
Zero structural HTML changes — only text content within marked elements is modified.

Usage:
    python update_prices.py              # Update index.html with live data
    python update_prices.py --dry-run    # Preview changes without writing
"""

import re
import sys
import logging
from datetime import datetime
from pathlib import Path

import yfinance as yf

# ── Configuration ──────────────────────────────────────────────────────────

HTML_FILE = Path(__file__).parent / "index.html"

TICKER_MAP = {
    "MP": "MP",
    "LYSCF": "LYSCF",
    "LYC_AX": "LYC.AX",
    "UUUU": "UUUU",
    "USAR": "USAR",
    "CRML": "CRML",
    "IRDM": "IRDM",
    "LHX": "LHX",
    "MTRN": "MTRN",
}

# Tickers that use AUD formatting (A$ prefix)
AUD_TICKERS = {"LYC_AX"}

# Fields that yfinance can provide
FIELDS = {
    "price": lambda info: info.get("currentPrice") or info.get("regularMarketPrice"),
    "mktcap": lambda info: info.get("marketCap"),
    "revenue": lambda info: info.get("totalRevenue"),
    "net_income": lambda info: info.get("netIncomeToCommon"),
    "52wk_high": lambda info: info.get("fiftyTwoWeekHigh"),
    "52wk_low": lambda info: info.get("fiftyTwoWeekLow"),
    "target_price": lambda info: info.get("targetMeanPrice"),
    "pe_forward": lambda info: info.get("forwardPE"),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("update_prices")

# ── Formatting ─────────────────────────────────────────────────────────────


def human_readable(n: float) -> str:
    """Convert large numbers to human-readable format: $10.86B, $232.7M, etc."""
    abs_n = abs(n)
    if abs_n >= 1e12:
        return f"{n / 1e12:.2f}T"
    if abs_n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if abs_n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if abs_n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return f"{n:.0f}"


def format_value(value, field: str, ticker_id: str) -> str:
    """Format a value for display in the HTML, matching existing formatting conventions."""
    prefix = "A$" if ticker_id in AUD_TICKERS else "$"

    if field == "price":
        return f"{prefix}{value:,.2f}"

    if field == "mktcap":
        return f"{prefix}{human_readable(value)}"

    if field == "revenue":
        if value == 0:
            return f"{prefix}0"
        return f"{prefix}{human_readable(value)}"

    if field == "net_income":
        if value < 0:
            return f"-{prefix}{human_readable(abs(value))}"
        return f"{prefix}{human_readable(value)}"

    if field == "target_price":
        return f"{prefix}{value:,.2f}"

    if field == "pe_forward":
        return f"{value:.1f}x"

    return str(value)


# ── Data Fetching ──────────────────────────────────────────────────────────


def fetch_all_data() -> dict:
    """Fetch stock data for all tickers from yfinance."""
    results = {}

    for ticker_id, yf_symbol in TICKER_MAP.items():
        try:
            log.info(f"Fetching {yf_symbol} (as {ticker_id})...")
            stock = yf.Ticker(yf_symbol)
            info = stock.info

            # Validate that we got real data
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if price is None:
                log.warning(f"  {yf_symbol}: No price data, skipping")
                continue

            results[ticker_id] = {
                "price": price,
                "mktcap": info.get("marketCap"),
                "revenue": info.get("totalRevenue"),
                "net_income": info.get("netIncomeToCommon"),
                "52wk_high": info.get("fiftyTwoWeekHigh"),
                "52wk_low": info.get("fiftyTwoWeekLow"),
                "target_price": info.get("targetMeanPrice"),
                "pe_forward": info.get("forwardPE"),
            }
            log.info(f"  {yf_symbol}: ${price:.2f}")

        except Exception as e:
            log.warning(f"  {yf_symbol}: Error — {e}")
            continue

    return results


# ── HTML Updating ──────────────────────────────────────────────────────────


def update_html(html: str, data: dict) -> str:
    """Update HTML content by replacing text inside data-attributed elements."""
    changes = 0
    skipped = 0

    for ticker_id, ticker_data in data.items():
        # Update simple fields (price, mktcap, revenue, net_income, target_price, pe_forward)
        for field in ("price", "mktcap", "revenue", "net_income", "target_price", "pe_forward"):
            value = ticker_data.get(field)
            if value is None:
                skipped += 1
                continue

            formatted = format_value(value, field, ticker_id)

            # Pattern: data-ticker="X" data-field="Y" ... > CONTENT <
            pattern = rf'(data-ticker="{ticker_id}"\s+data-field="{field}"[^>]*>)[^<]*(<)'
            new_html = re.sub(pattern, rf"\g<1>{formatted}\2", html)

            # Also handle reversed attribute order
            pattern_rev = rf'(data-field="{field}"\s+data-ticker="{ticker_id}"[^>]*>)[^<]*(<)'
            new_html = re.sub(pattern_rev, rf"\g<1>{formatted}\2", new_html)

            if new_html != html:
                count = len(re.findall(pattern, html)) + len(re.findall(pattern_rev, html))
                log.info(f"  {ticker_id}.{field} → {formatted} ({count} element(s))")
                changes += count
                html = new_html

        # Update 52-week range (composite field from 52wk_high + 52wk_low)
        high = ticker_data.get("52wk_high")
        low = ticker_data.get("52wk_low")
        if high is not None and low is not None:
            prefix = "A$" if ticker_id in AUD_TICKERS else "$"
            low_fmt = f"{prefix}{low:,.2f}"
            high_fmt = f"{prefix}{high:,.2f}"
            new_range = f"52wk: {low_fmt} – {high_fmt}"

            # Match the 52wk_range field, preserving any suffix after the range
            pattern = rf'(data-ticker="{ticker_id}"\s+data-field="52wk_range"[^>]*>)[^<]*(<)'

            def range_replacer(m):
                old_text = html[m.start(1) + len(m.group(1)):m.start(2)]
                # For LYSCF, preserve OTC prefix
                otc_match = re.search(r"^US OTC: ~\$[\d.]+ · ", old_text)
                otc_prefix = ""
                if otc_match:
                    lyscf_data = data.get("LYSCF", {})
                    lyscf_price = lyscf_data.get("price")
                    if lyscf_price is not None:
                        otc_prefix = f"US OTC: ~${lyscf_price:.2f} · "
                    else:
                        otc_prefix = otc_match.group(0)
                # Preserve suffix AFTER the 52wk range (e.g., " · ATH $100.25")
                # Match past "52wk: $X – $Y" then capture any trailing text
                suffix_match = re.search(r"52wk: [^·<]+(· .+)$", old_text)
                suffix = " " + suffix_match.group(1) if suffix_match else ""
                return m.group(1) + otc_prefix + new_range + suffix + m.group(2)

            new_html = re.sub(pattern, range_replacer, html)

            # Also handle reversed attribute order
            pattern_rev = rf'(data-field="52wk_range"\s+data-ticker="{ticker_id}"[^>]*>)[^<]*(<)'
            new_html = re.sub(pattern_rev, range_replacer, new_html)

            if new_html != html:
                log.info(f"  {ticker_id}.52wk_range → {new_range}")
                changes += 1
                html = new_html

        # Update net_income color class (swap g/r based on positive/negative)
        net_income = ticker_data.get("net_income")
        if net_income is not None:
            # In snap-grid: class="val r" or class="val g" or class="val a"
            # Swap to 'r' if negative, 'g' if positive
            new_class = "r" if net_income < 0 else "g"
            # Match val elements with a color class for this ticker's net_income
            color_pattern = rf'(class="val )[rga](" data-ticker="{ticker_id}" data-field="net_income")'
            html = re.sub(color_pattern, rf"\g<1>{new_class}\2", html)
            # Also handle data attrs before class (reversed)
            color_pattern2 = rf'(data-ticker="{ticker_id}" data-field="net_income"[^>]*class="val )[rga](")'
            html = re.sub(color_pattern2, rf"\g<1>{new_class}\2", html)

            # In overview table: class="mono r" or "mono g"
            ov_pattern = rf'(class="mono )[rga](" data-ticker="{ticker_id}" data-field="net_income")'
            html = re.sub(ov_pattern, rf"\g<1>{new_class}\2", html)

    # Update timestamp
    now = datetime.now().strftime("%b %d, %Y %I:%M %p ET")
    html = re.sub(
        r'(data-field="last-updated"[^>]*>)[^<]*(<)',
        rf"\1Prices last updated: {now}\2",
        html,
    )

    # Update price date labels
    date_label = datetime.now().strftime("Price (%b %d)")
    html = re.sub(
        r'(data-field="price_date"[^>]*>)[^<]*(<)',
        rf"\1{date_label}\2",
        html,
    )

    log.info(f"Summary: {changes} fields updated, {skipped} skipped (no data)")
    return html


# ── Main ───────────────────────────────────────────────────────────────────


def main():
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        log.info("DRY RUN — no files will be modified")

    if not HTML_FILE.exists():
        log.error(f"HTML file not found: {HTML_FILE}")
        sys.exit(1)

    # Fetch data
    log.info(f"Fetching data for {len(TICKER_MAP)} tickers...")
    data = fetch_all_data()
    log.info(f"Got data for {len(data)}/{len(TICKER_MAP)} tickers")

    if not data:
        log.error("No data fetched, exiting")
        sys.exit(1)

    # Read HTML
    html = HTML_FILE.read_text(encoding="utf-8")
    original_html = html

    # Update
    html = update_html(html, data)

    if html == original_html:
        log.info("No changes detected")
        return

    if dry_run:
        log.info("DRY RUN complete — no files written")
        return

    # Write
    HTML_FILE.write_text(html, encoding="utf-8")
    log.info(f"Updated {HTML_FILE}")


if __name__ == "__main__":
    main()
