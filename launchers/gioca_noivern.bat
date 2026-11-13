@echo off
REM Parte gia' al liv.8: NOIVERN (Volante/Drago) con Ecolocalizzazione.
REM R a scelta: Tifone / Dragobolide.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/noibat.json --level 8
