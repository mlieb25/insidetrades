#!/usr/bin/env python3
"""End-to-end test of the trade monitoring pipeline.

Tests with real Form 4 XML data from SEC EDGAR, plus a synthetic
high-conviction purchase to demonstrate signal generation.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trade_monitor.edgar_poller import parse_form4_xml, poll_atom_feed
from trade_monitor.scorer import score_trade
from trade_monitor.portfolio import PaperPortfolio
from trade_monitor.notifier import format_signal_alert
from trade_monitor.market_data import save_market_data
from trade_monitor.models import InsiderTrade
from trade_monitor import config, state as store

# ── Real Form 4 XML from SSRM filing (tax withholding — should be filtered) ──
REAL_FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
    <schemaVersion>X0609</schemaVersion>
    <documentType>4</documentType>
    <periodOfReport>2026-04-01</periodOfReport>
    <issuer>
        <issuerCik>0000921638</issuerCik>
        <issuerName>SSR MINING INC.</issuerName>
        <issuerTradingSymbol>SSRM</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0001961807</rptOwnerCik>
            <rptOwnerName>MacNevin William K.</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>0</isDirector>
            <isOfficer>0</isOfficer>
            <isTenPercentOwner>0</isTenPercentOwner>
            <isOther>1</isOther>
            <otherText>EVP, Ops &amp; Sustainability</otherText>
        </reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <securityTitle><value>Common Shares</value></securityTitle>
            <transactionDate><value>2026-04-01</value></transactionDate>
            <transactionCoding>
                <transactionFormType>4</transactionFormType>
                <transactionCode>F</transactionCode>
                <equitySwapInvolved>0</equitySwapInvolved>
            </transactionCoding>
            <transactionAmounts>
                <transactionShares><value>7382</value></transactionShares>
                <transactionPricePerShare><value>31.62</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>246729</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
    <footnotes>
        <footnote id="F1">Represents shares withheld to satisfy tax withholding obligations.</footnote>
    </footnotes>
</ownershipDocument>"""

# ── Synthetic high-conviction purchase (CEO buying $2M in open market) ──
SYNTHETIC_PURCHASE_XML = """<?xml version="1.0"?>
<ownershipDocument>
    <schemaVersion>X0609</schemaVersion>
    <documentType>4</documentType>
    <periodOfReport>2026-04-01</periodOfReport>
    <issuer>
        <issuerCik>0000789019</issuerCik>
        <issuerName>MICROSOFT CORP</issuerName>
        <issuerTradingSymbol>MSFT</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0001234567</rptOwnerCik>
            <rptOwnerName>Nadella Satya</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>1</isDirector>
            <isOfficer>1</isOfficer>
            <isTenPercentOwner>0</isTenPercentOwner>
            <isOther>0</isOther>
            <officerTitle>Chairman &amp; CEO</officerTitle>
        </reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeTransaction>
            <securityTitle><value>Common Stock</value></securityTitle>
            <transactionDate><value>2026-04-01</value></transactionDate>
            <transactionCoding>
                <transactionFormType>4</transactionFormType>
                <transactionCode>P</transactionCode>
                <equitySwapInvolved>0</equitySwapInvolved>
            </transactionCoding>
            <transactionAmounts>
                <transactionShares><value>5000</value></transactionShares>
                <transactionPricePerShare><value>400.50</value></transactionPricePerShare>
                <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
            </transactionAmounts>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>25000</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
            <ownershipNature>
                <directOrIndirectOwnership><value>D</value></directOrIndirectOwnership>
            </ownershipNature>
        </nonDerivativeTransaction>
    </nonDerivativeTable>
    <footnotes/>
</ownershipDocument>"""


def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def main():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.LOG_DIR, exist_ok=True)

    # ── Test 1: Parse real Form 4 (should be filtered as non-purchase) ──
    separator("TEST 1: Parse Real Form 4 (Tax Withholding — Code F)")

    trades = parse_form4_xml(REAL_FORM4_XML,
                             index_url="https://www.sec.gov/Archives/edgar/data/921638/000196180726000007/0001961807-26-000007-index.htm")

    for t in trades:
        print(f"Ticker:       {t.ticker}")
        print(f"Insider:      {t.owner_name} ({t.insider_role})")
        print(f"Tx Code:      {t.transaction_code}")
        print(f"Shares:       {t.shares:,.0f}")
        print(f"Price:        ${t.price_per_share:.2f}")
        print(f"Dollar Value: ${t.dollar_value:,.0f}")
        print(f"Is Purchase:  {t.is_open_market_purchase}")
        print(f"Qualifies:    {t.transaction_code in config.QUALIFYING_TX_CODES}")

        # Score it
        signal = score_trade(t)
        print(f"\nSignal Score: {signal.score:.0f}/100")
        print(f"Classification: {signal.classification}")
        print(f"Status:       {signal.status}")
        if signal.rejected_reason:
            print(f"Rejected:     {signal.rejected_reason}")
        print(f"Breakdown:    {json.dumps(signal.score_breakdown, indent=2)}")

    # ── Test 2: Parse synthetic CEO purchase ──
    separator("TEST 2: Synthetic CEO Open-Market Purchase ($2M)")

    # Pre-cache market data for MSFT
    save_market_data("MSFT", {
        "price": 402.00,
        "changesPercentage": 0.8,
        "marketCap": 3_000_000_000_000,
        "pe": 35.2,
        "volume": 22_000_000,
        "avgVolume": 20_000_000,
        "dayLow": 398.50,
        "dayHigh": 404.00,
        "yearLow": 340.00,
        "yearHigh": 430.00,
        "previousClose": 399.50,
    })

    trades2 = parse_form4_xml(SYNTHETIC_PURCHASE_XML,
                              index_url="https://www.sec.gov/Archives/edgar/data/789019/test-index.htm")

    for t in trades2:
        print(f"Ticker:       {t.ticker}")
        print(f"Insider:      {t.owner_name} ({t.insider_role})")
        print(f"Tx Code:      {t.transaction_code}")
        print(f"Shares:       {t.shares:,.0f}")
        print(f"Price:        ${t.price_per_share:.2f}")
        print(f"Dollar Value: ${t.dollar_value:,.0f}")
        print(f"Is Purchase:  {t.is_open_market_purchase}")
        print()

        # Score with real market context
        signal = score_trade(t)
        print(f"Signal Score:    {signal.score:.0f}/100")
        print(f"Confidence:      {signal.confidence}")
        print(f"Classification:  {signal.classification}")
        print(f"Direction:       {signal.direction}")
        print(f"Entry Zone:      ${signal.entry_zone_low:.2f} – ${signal.entry_zone_high:.2f}")
        print(f"Stop Loss:       ${signal.stop_loss:.2f}")
        print(f"Take Profit:     ${signal.take_profit:.2f}")
        print(f"Trailing Stop:   {signal.trailing_stop_pct:.1f}%")
        print(f"Position Size:   {signal.position_size_pct:.1f}% of capital")
        print(f"Max Hold:        {signal.max_holding_days} days")
        print()

        print("Reasons:")
        for r in signal.reasons:
            print(f"  • {r}")
        print()
        print("Score Breakdown:")
        for factor, pts in signal.score_breakdown.items():
            print(f"  {factor:25s} {pts:5.1f}")

        # ── Test 3: Execute paper trade ──
        if signal.classification == "REPLICATE":
            separator("TEST 3: Paper Trade Execution")

            portfolio = PaperPortfolio()
            position = portfolio.open_position(signal)
            if position:
                print(f"Position Opened:")
                print(f"  ID:         {position.position_id}")
                print(f"  Ticker:     {position.ticker}")
                print(f"  Direction:  {position.direction}")
                print(f"  Entry:      ${position.entry_price:.2f}")
                print(f"  Shares:     {position.shares}")
                print(f"  Cost:       ${position.entry_price * position.shares:,.2f}")
                print(f"  Stop:       ${position.stop_price:.2f}")
                print(f"  Target:     ${position.target_price:.2f}")
                print(f"  Max Exit:   {position.max_exit_date}")
                print()

                summary = portfolio.get_summary()
                print(f"Portfolio After:")
                print(f"  Cash:       ${summary['cash']:,.2f}")
                print(f"  Positions:  {summary['open_positions']}")
                print(f"  Total:      ${summary['total_value']:,.2f}")

            # ── Test 4: Generate alert ──
            separator("TEST 4: Signal Alert Notification")
            alert = format_signal_alert(signal)
            print(f"Subject: {alert['subject']}")
            print()
            print(alert['body_text'])

    # ── Test 5: Live Atom Feed Check ──
    separator("TEST 5: Live EDGAR Atom Feed Check")
    print("Polling SEC EDGAR for latest Form 4 filings...")
    entries = poll_atom_feed()
    print(f"Found {len(entries)} entries in the Atom feed:")
    for acc, title, url, ts in entries[:5]:
        print(f"  [{ts}] {title}")
        print(f"    Accession: {acc}")
        print(f"    URL: {url}")
        print()

    separator("ALL TESTS COMPLETE")
    print(f"Data dir: {config.DATA_DIR}")
    print(f"Log dir:  {config.LOG_DIR}")


if __name__ == "__main__":
    main()
