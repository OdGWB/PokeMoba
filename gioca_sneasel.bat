@echo off
REM Parte al liv.1: SNEASEL (Buio/Ghiaccio) con la passiva Sole e Luna.
REM Oro dai minion -> Weavile al liv.8; oro dai neutrali -> Sneasler.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/sneasel.json
