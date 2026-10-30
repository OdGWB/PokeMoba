@echo off
REM Parte gia' al liv.8: URSALUNA (Terra/Normale) con Miele + Dentistretti.
REM R a scelta: Luna Piena / Terremoto.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/teddiursa.json --level 8
