@echo off
REM ARCHALUDON (Acciaio/Drago), gia' al liv.8.
REM R a scelta: Elettroraggio / Tuono.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/duraludon.json --level 8
