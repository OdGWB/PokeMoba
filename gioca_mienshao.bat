@echo off
REM MIENSHAO (Lotta), gia' al liv.8: portata +40%.
REM R a scelta: Danza delle Maniche / Contropiede.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/mienfoo.json --level 8
