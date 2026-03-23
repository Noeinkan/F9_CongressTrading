# Congress Trading (House + Senate)

Tracker per disclosure pubbliche del Congresso che acquisisce PTR e filing metadata, conserva i documenti raw, normalizza transazioni e asset in SQLite, ed esporta un dataset pronto per analisi e dashboard.

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

L'autodownload dei PTR House in questo repository e limitato ai filing year 2025 e 2026.

## Dove trovare i PDF
- House: usa il portale ufficiale del Clerk della House su https://disclosures-clerk.house.gov/PublicDisclosure/FinancialDisclosure. I file FD annuali sono scaricabili in blocco, ma i PTR spesso non hanno un link bulk stabile. In pratica conviene usare la ricerca del portale, aprire il report Periodic Transaction Report del membro interessato e salvare il PDF sotto `data/raw/house/<anno>/`.
- Senate: usa il portale ufficiale eFD su https://efdsearch.senate.gov/search/. Devi prima accettare i termini di utilizzo, poi puoi cercare i filing dal 2012 in avanti. Filtra o cerca i Periodic Transaction Report, apri il filing e salva il PDF sotto `data/raw/senate/<anno>/`.
- Il parser cerca ricorsivamente qualsiasi file `.pdf` dentro `data/raw/house/` e `data/raw/senate/`, quindi le sottocartelle per anno sono consigliate ma non obbligatorie.
- Se hai archivi `.zip`, puoi anche copiarli in `data/raw/`, `data/raw/house/` o `data/raw/senate/`: la pipeline prova a estrarli automaticamente prima del parsing.

## Setup rapido Windows
- Esegui `powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1 ingest-all` per installare le dipendenze nel venv del progetto e lanciare l’ingestione.
- Se vuoi un comando diverso, sostituisci `ingest-all` con ad esempio `dashboard`, `export-csv`, `ingest-house` o `ingest-senate`.
- In VS Code puoi usare direttamente i task workspace `Ingest All (venv)` e `Dashboard (venv)` per eseguire sempre il progetto con `.venv\Scripts\python.exe`.

## Comandi principali
- Ingest House 2022+: `python -m src.main ingest-house`
- Ingest Senate 2022+: `python -m src.main ingest-senate`
- Esegui tutto: `python -m src.main ingest-all`
- Export CSV: `python -m src.main export-csv --out data/congress_trades.csv`
- Export review queue: `python -m src.main export-review-csv --out data/review_queue.csv`
- Dashboard: `python -m src.main dashboard`

## Stato attuale
Il repository ora mantiene due livelli di storage:

1. tabelle legacy per compatibilita (`trades`, `fd_filings`)
2. schema normalizzato per il tracker:
	- `members`
	- `filings`
	- `transactions`
	- `issuers`
	- `transaction_tags`
	- `review_queue`
	- `asset_resolution_cache`

Questo permette di conservare l'asset raw dichiarato, un ticker se risolvibile, un `confidence_score`, e uno `review_status` per distinguere match esatti, match fuzzy e casi da revisione manuale.

## Risoluzione asset
La pipeline di resolution classifica ogni asset in una di tre categorie:
- `exact_match`: nome/ticker risolto con corrispondenza canonica affidabile; non entra in review queue per la sola resolution
- `fuzzy_match`: ticker trovato ma con corrispondenza approssimata; resta disponibile nel dataset ma viene messo in review queue
- `manual_review`: nessun ticker affidabile; il record viene trattenuto per revisione manuale

La cache `asset_resolution_cache` persiste anche questa classificazione, cosi le riesecuzioni non ricadono ogni volta sugli stessi lookup esterni.

## Schema CSV
Colonne principali dell'export normalizzato:
- `member`
- `chamber`
- `filing_type`
- `filing_date`
- `transaction_date`
- `owner_type`
- `asset_name_raw`
- `asset_name_normalized`
- `asset_type`
- `issuer_name`
- `ticker`
- `transaction_type`
- `amount_low`
- `amount_high`
- `amount_range_raw`
- `confidence_score`
- `review_status`
- `source_url`
- `raw_document_path`

## Limiti correnti
- il parser PTR resta euristico e dipende dalla struttura del PDF
- la risoluzione degli asset distingue ora exact match, fuzzy match e manual review, ma resta limitata dalla qualita dei nomi dichiarati nei PDF
- i fuzzy match vengono esportati con ticker e tenuti in review queue; i manual review restano senza ticker finche non vengono corretti a valle
- non esiste ancora un sistema di alert; la dashboard Streamlit e il primo layer di analisi sopra il backend normalizzato

## Dashboard Streamlit
La prima dashboard legge prima dallo SQLite normalizzato (`members`, `filings`, `transactions`, `review_queue`) e, se non trova righe, prova i CSV esportati.

Vista iniziale inclusa:
- KPI su volume transazioni, membri attivi, ticker risolti e review aperte
- timeline mensile dell'attivita
- ranking di membri e ticker
- filtri per camera, tipo transazione, tipo asset, review status, data e testo libero
- pannello review queue per casi irrisolti o derivati dal `review_status`
- tabella raw con download CSV del subset filtrato

Avvio:
- `python -m src.main dashboard`
- oppure `streamlit run streamlit_app.py`
- in VS Code: task `Dashboard (venv)`

## Troubleshooting interprete VS Code
Se vedi errori come `ModuleNotFoundError: No module named 'dateutil'`, il problema di solito non e nel repository ma nell'interprete Python usato dalla sessione corrente.

Checklist rapida:
1. seleziona l'interprete del workspace: `.venv\Scripts\python.exe`
2. chiudi i terminali gia aperti e aprine uno nuovo dopo il cambio interprete
3. usa i task `Ingest All (venv)` o `Dashboard (venv)` invece di lanciare `python` generico

Nota: in questo workspace `.vscode/settings.json` punta gia al venv locale, ma un terminale aperto prima del cambio puo continuare a usare un Python globale.

Se il database e vuoto:
1. `python -m src.main ingest-all`
2. `python -m src.main export-csv --out data/congress_trades.csv`
3. `python -m src.main dashboard`
