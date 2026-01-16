# Congress Trading (House + Senate) – PTR → SQLite → CSV

Pipeline per scaricare e normalizzare i Periodic Transaction Reports (PTR) dal 2022 in poi (House + Senate), con lookup automatico dei ticker e caching locale. Output finale esportabile in CSV.

## Requisiti
- Python 3.10+
- API key Polygon (gratuita) per il ticker mapping
- (Opzionale) API key OpenFIGI per fallback mapping

Imposta le variabili d’ambiente:
- `POLYGON_API_KEY`
- `OPENFIGI_API_KEY` (opzionale)

## Struttura
- `src/` codice
- `data/raw/house/` PDF House
- `data/raw/senate/` PDF Senate
- `data/db/` SQLite
- `data/cache/` cache lookup ticker

## Note legali
- Senate eFD richiede accettazione dei termini. Il downloader è progettato per uso conforme; verifica i termini prima dell’uso.

## Nota House (PTR)
Se i link bulk PTR non sono esposti dal sito, l’ingestione House passa in modalità manuale: scarica i PDF dal portale House e salvali in data/raw/house/ (dal 2022 in poi), poi riesegui il comando.

## Comandi principali
- Ingest House 2022+: `python -m src.main ingest-house`
- Ingest Senate 2022+: `python -m src.main ingest-senate`
- Esegui tutto: `python -m src.main ingest-all`
- Export CSV: `python -m src.main export-csv --out data/congress_trades.csv`

## Schema CSV
Colonne:
- `member`
- `chamber`
- `filing_date`
- `transaction_date`
- `asset`
- `ticker`
- `transaction_type`
- `amount_range`
- `source_url`
