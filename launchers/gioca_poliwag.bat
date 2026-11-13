@echo off
REM Poliwag dal livello 1: evolve in Poliwhirl al liv.4 e, al liv.8, in POLIWRATH
REM (oppure in POLITOAD se compri la Roccia di Re in base prima del liv.8).
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/poliwag.json
