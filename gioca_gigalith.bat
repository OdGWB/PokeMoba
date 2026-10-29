@echo off
REM Parte gia' al liv.8: GIGALITH (Roccia, tank di ingaggio stile Ornn) con la
REM tempesta di Sabbiafiume attiva. R a scelta: Frana / Esplosione.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/roggenrola.json --level 8
