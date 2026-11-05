@echo off
REM OCTILLERY (Acqua), gia' al liv.8.
REM R a scelta: Iper Raggio / Presa a Ventosa.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/remoraid.json --level 8
