@echo off
REM FLABEBE (Folletto): Giardino (fiori che gli alleati raccolgono), Semina,
REM Florocura, Petalbufera. Al liv.4 Floette, al liv.8 Florges.
REM Colore dei fiori: --colore rosso/giallo/arancione/blu/bianco
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/flabebe.json --colore rosso
