@echo off
REM Roggenrola dal livello 1: evolve in Boldore al liv.4 e in GIGALITH al liv.8
REM (Roccia, tank di ingaggio: pilastri, carica, lancio in aria; passiva Sabbiafiume).
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/roggenrola.json
