@echo off
REM Parte gia' al liv.8: CORVIKNIGHT (Volante/Acciaio) con Specchiarmatura.
REM R a scelta: Taxi Volante / Baldeali.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/rookidee.json --level 8
