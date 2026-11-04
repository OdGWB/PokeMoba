@echo off
REM MAGNEMITE (Elettro/Acciaio): Magnetismo (cariche + / - che si attraggono
REM o respingono), Tuonoshock, Campo Magnetico, Voltcambio.
REM Al liv.4 Magneton, al liv.8 Magnezone.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/magnemite.json
