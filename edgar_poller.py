"""SEC EDGAR Form 4 polling engine.

Primary source: EDGAR Atom feed for latest ownership filings.
Backup source: EDGAR EFTS search API for batch recovery.
"""
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Set
from urllib.parse import urljoin

import requests

from . import config
from .models import Filing, InsiderTrade
from .logger import log_filing, log_error, log_system

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_last_request_time = 0.0


def _rate_limit():
    """Enforce SEC rate limit of 10 requests/second."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    wait = (1.0 / config.SEC_RATE_LIMIT_PER_SEC) - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_request_time = time.time()


def _get(url: str, timeout: int = 30) -> Optional[requests.Response]:
    """GET request with rate limiting and error handling."""
    _rate_limit()
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": config.USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        log_error(f"HTTP error fetching {url}: {e}")
        return None


# ── Atom Feed Polling ─────────────────────────────────────────────────

def poll_atom_feed() -> List[Tuple[str, str, str, str]]:
    """Poll the EDGAR latest-filings Atom feed for Form 4s.

    Returns list of (accession_no, title, index_url, updated_timestamp).
    """
    resp = _get(config.SEC_ATOM_URL)
    if not resp:
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        log_error(f"XML parse error on Atom feed: {e}")
        return []

    entries = root.findall("atom:entry", ATOM_NS)
    results = []
    seen_accessions = set()

    for entry in entries:
        title_el = entry.find("atom:title", ATOM_NS)
        link_el = entry.find("atom:link", ATOM_NS)
        updated_el = entry.find("atom:updated", ATOM_NS)
        id_el = entry.find("atom:id", ATOM_NS)

        if title_el is None or link_el is None:
            continue

        title = title_el.text or ""
        if not title.startswith("4 "):
            continue

        index_url = link_el.get("href", "")
        updated = updated_el.text if updated_el is not None else ""

        # Extract accession number from the ID or URL
        acc_no = ""
        if id_el is not None and id_el.text:
            m = re.search(r"accession-number=(\S+)", id_el.text)
            if m:
                acc_no = m.group(1)
        if not acc_no:
            m = re.search(r"(/\d{10}-\d{2}-\d{6})", index_url)
            if m:
                acc_no = m.group(1).strip("/").replace("/", "-")

        if acc_no and acc_no not in seen_accessions:
            seen_accessions.add(acc_no)
            results.append((acc_no, title, index_url, updated))

    return results


# ── Filing XML Discovery & Parsing ────────────────────────────────────

def find_xml_url(index_url: str) -> Optional[str]:
    """From a filing index URL, find the Form 4 XML document URL."""
    # Convert index URL to the directory listing
    # index_url looks like: https://www.sec.gov/Archives/edgar/data/.../...-index.htm
    base = index_url.rsplit("/", 1)[0] + "/"

    resp = _get(index_url)
    if not resp:
        return None

    # Look for XML file links in the index page
    # Pattern: href="...form4...xml" or similar
    xml_patterns = [
        r'href="([^"]*form4[^"]*\.xml)"',
        r'href="([^"]*\.xml)"',
    ]

    for pattern in xml_patterns:
        matches = re.findall(pattern, resp.text, re.IGNORECASE)
        for match in matches:
            # Skip XBRL viewer links (xslF345X06)
            if "xsl" in match.lower():
                continue
            if match.startswith("http"):
                return match
            elif match.startswith("/"):
                return "https://www.sec.gov" + match
            else:
                return urljoin(base, match)

    return None


def parse_form4_xml(xml_content: str, index_url: str = "",
                    filing_timestamp: str = "") -> List[InsiderTrade]:
    """Parse a Form 4 XML document into InsiderTrade objects.

    A single Form 4 can contain multiple transactions.
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        log_error(f"XML parse error: {e}")
        return []

    trades = []

    # ── Issuer info ───────────────────────────────────────────────
    issuer = root.find("issuer")
    issuer_cik = _text(issuer, "issuerCik") if issuer is not None else ""
    issuer_name = _text(issuer, "issuerName") if issuer is not None else ""
    ticker = _text(issuer, "issuerTradingSymbol") if issuer is not None else ""

    # ── Owner info ────────────────────────────────────────────────
    owner = root.find("reportingOwner")
    owner_name = ""
    owner_cik = ""
    is_director = False
    is_officer = False
    is_ten_pct = False
    is_other = False
    role_text = ""

    if owner is not None:
        oid = owner.find("reportingOwnerId")
        if oid is not None:
            owner_cik = _text(oid, "rptOwnerCik")
            owner_name = _text(oid, "rptOwnerName")

        rel = owner.find("reportingOwnerRelationship")
        if rel is not None:
            is_director = _text(rel, "isDirector") == "1"
            is_officer = _text(rel, "isOfficer") == "1"
            is_ten_pct = _text(rel, "isTenPercentOwner") == "1"
            is_other = _text(rel, "isOther") == "1"
            role_text = _text(rel, "officerTitle") or _text(rel, "otherText") or ""

    # ── Filing metadata ───────────────────────────────────────────
    period = _text(root, "periodOfReport")
    filing_date = period or ""
    doc_type = _text(root, "documentType")

    # ── Footnotes ─────────────────────────────────────────────────
    footnotes_map = {}
    fn_section = root.find("footnotes")
    if fn_section is not None:
        for fn in fn_section.findall("footnote"):
            fid = fn.get("id", "")
            footnotes_map[fid] = (fn.text or "").strip()

    # ── Non-Derivative Transactions ───────────────────────────────
    nd_table = root.find("nonDerivativeTable")
    if nd_table is not None:
        for tx in nd_table.findall("nonDerivativeTransaction"):
            trade = _parse_transaction(
                tx, issuer_cik, issuer_name, ticker,
                owner_name, owner_cik,
                is_director, is_officer, is_ten_pct, is_other, role_text,
                filing_date, index_url, filing_timestamp, footnotes_map,
            )
            if trade:
                trades.append(trade)

    return trades


def _parse_transaction(
    tx, issuer_cik, issuer_name, ticker,
    owner_name, owner_cik,
    is_director, is_officer, is_ten_pct, is_other, role_text,
    filing_date, index_url, filing_timestamp, footnotes_map,
) -> Optional[InsiderTrade]:
    """Parse a single nonDerivativeTransaction element."""

    security_title = _nested_value(tx, "securityTitle")
    tx_date = _nested_value(tx, "transactionDate")

    coding = tx.find("transactionCoding")
    tx_code = _text(coding, "transactionCode") if coding is not None else ""

    amounts = tx.find("transactionAmounts")
    shares_str = _nested_value(amounts, "transactionShares") if amounts is not None else "0"
    price_str = _nested_value(amounts, "transactionPricePerShare") if amounts is not None else "0"
    acq_disp = _nested_value(amounts, "transactionAcquiredDisposedCode") if amounts is not None else ""

    post = tx.find("postTransactionAmounts")
    shares_after_str = _nested_value(post, "sharesOwnedFollowingTransaction") if post is not None else "0"

    own_nature = tx.find("ownershipNature")
    ownership = _nested_value(own_nature, "directOrIndirectOwnership") if own_nature is not None else "D"

    # Collect footnote IDs referenced in this transaction
    fn_ids = set()
    for el in tx.iter():
        for fn_ref in el.findall("footnoteId"):
            fn_ids.add(fn_ref.get("id", ""))
    footnotes = [footnotes_map.get(fid, "") for fid in sorted(fn_ids) if fid in footnotes_map]

    # Parse numeric values safely
    shares = _safe_float(shares_str)
    price = _safe_float(price_str)
    shares_after = _safe_float(shares_after_str)

    # Build accession number from index URL
    acc_match = re.search(r"(\d{10}-\d{2}-\d{6})", index_url)
    acc_no = acc_match.group(1) if acc_match else ""

    return InsiderTrade(
        accession_no=acc_no,
        filing_url=index_url,
        index_url=index_url,
        source="SEC_EDGAR",
        issuer_cik=issuer_cik,
        issuer_name=issuer_name,
        ticker=ticker.upper().strip() if ticker else "",
        owner_name=owner_name,
        owner_cik=owner_cik,
        is_director=is_director,
        is_officer=is_officer,
        is_ten_pct_owner=is_ten_pct,
        is_other=is_other,
        role_text=role_text,
        transaction_code=tx_code,
        transaction_date=tx_date,
        filing_date=filing_date,
        security_title=security_title,
        shares=shares,
        price_per_share=price,
        acquired_or_disposed=acq_disp,
        shares_after=shares_after,
        ownership_type=ownership,
        footnotes=footnotes,
        filing_timestamp=filing_timestamp,
    )


# ── EFTS Batch Recovery ───────────────────────────────────────────────

def batch_search_form4s(start_date: str, end_date: str,
                        max_results: int = 200) -> List[dict]:
    """Use EDGAR EFTS search to find Form 4 filings in a date range.

    Returns raw hit metadata dicts.
    """
    url = (
        f"{config.SEC_EFTS_URL}?"
        f'q=""&forms=4&dateRange=custom'
        f"&startdt={start_date}&enddt={end_date}"
    )
    resp = _get(url)
    if not resp:
        return []

    try:
        data = resp.json()
    except ValueError:
        return []

    hits = data.get("hits", {}).get("hits", [])
    return [h.get("_source", {}) for h in hits[:max_results]]


# ── Full Poll Cycle ───────────────────────────────────────────────────

def poll_new_filings(seen: Set[str]) -> Tuple[List[InsiderTrade], Set[str]]:
    """Run one poll cycle: fetch Atom feed, parse new filings.

    Returns (list of new InsiderTrade objects, updated seen set).
    """
    entries = poll_atom_feed()
    new_trades = []
    new_seen = set(seen)

    for acc_no, title, index_url, updated in entries:
        if acc_no in seen:
            continue

        new_seen.add(acc_no)
        log_filing(f"New Form 4 detected: {title}", {
            "accession_no": acc_no,
            "index_url": index_url,
            "updated": updated,
        })

        # Find and fetch the XML document
        xml_url = find_xml_url(index_url)
        if not xml_url:
            log_error(f"Could not find XML for {acc_no}", {"index_url": index_url})
            continue

        resp = _get(xml_url)
        if not resp:
            continue

        trades = parse_form4_xml(resp.text, index_url, updated)
        for t in trades:
            log_filing(f"Parsed trade: {t.owner_name} {t.transaction_code} "
                       f"{t.shares} shares of {t.ticker} @ ${t.price_per_share}",
                       t.to_dict())

        new_trades.extend(trades)

    return new_trades, new_seen


# ── Helpers ───────────────────────────────────────────────────────────

def _text(parent, tag: str) -> str:
    """Get text content of a child element."""
    if parent is None:
        return ""
    el = parent.find(tag)
    return (el.text or "").strip() if el is not None else ""


def _nested_value(parent, tag: str) -> str:
    """Get the <value> sub-element text of a named element."""
    if parent is None:
        return ""
    el = parent.find(tag)
    if el is None:
        return ""
    val = el.find("value")
    return (val.text or "").strip() if val is not None else ""


def _safe_float(s: str) -> float:
    """Parse a string to float, returning 0 on failure."""
    try:
        return float(s.replace(",", "")) if s else 0.0
    except (ValueError, TypeError):
        return 0.0
