@echo off
REM VENOMOTH (Coleottero/Veleno), gia' al liv.8.
REM R a scelta: Eledanza / Tempesta di Polveri.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/venonat.json --level 8
