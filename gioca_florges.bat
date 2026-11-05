@echo off
REM FLORGES (Folletto), gia' al liv.8, fiori gialli.
REM R a scelta: Giardino Reale / Solarraggio.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/flabebe.json --level 8 --colore giallo
