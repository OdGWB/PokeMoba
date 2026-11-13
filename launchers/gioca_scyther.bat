@echo off
REM SCYTHER (Coleottero/Volante) dal liv.1: compra Metalcoperta o Augite Nera
REM e al liv.8 evolve in Scizor o Kleavor.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/scyther.json
