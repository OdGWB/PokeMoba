@echo off
REM Avvia PokeMoba dal menu: scegli la mappa, poi il tuo Pokemon (gli altri
REM slot ricevono Pokemon casuali dal pool, senza ripetizioni).
cd /d "%~dp0"
python run_client.py
