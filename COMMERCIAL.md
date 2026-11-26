# Commercial audit

## Description
Congress Trading ingests U.S. public financial disclosures (House and Senate trade reports, OGE executive forms) from PDFs, normalises them into one database and resolves the declared assets to stock tickers. A FastAPI + React dashboard lets you browse members, tickers, trading patterns and a review queue.

## Problem and buyers
Problem: congressional and executive disclosures are published as layout-fragile PDFs on separate government portals, with free-text asset names and no API that aggregates them (product.md, "Problem it Solves").
Who might pay: Not found in the docs — product.md lists data analysts, hobbyist investors and researchers as inferred users and states "No code or doc identifies commercial enterprise customers, paying subscribers, or third-party API consumers".

## Stage
production

## Customer demos
unknown — an open demo is live at congress.demos.noeinsolutions.com/demo (16 Sep 2026); the email gate that would record who used it is built but not deployed (docs/DEMO.md)

## Commercial evidence
level: 1
- Pain point described (product.md)
- Public demo live, but without sign-up tracking, so no visitors are recorded (docs/DEMO.md)
- Explicitly no paying subscribers or API consumers identified (product.md)

## Technical value
Heuristic PDF parsing across three disclosure regimes into one schema, asset-to-ticker resolution with confidence tiers (Polygon, OpenFIGI), idempotent ingestion and a coverage audit.

## Sources
- product.md, docs/DEMO.md, README.md
