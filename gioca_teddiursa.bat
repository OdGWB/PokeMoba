@echo off
REM TEDDIURSA (Normale), jungler combattente con la passiva Miele.
REM Evolve in Ursaring al liv.4 e in Ursaluna al liv.8.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/teddiursa.json
