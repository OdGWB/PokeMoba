@echo off
REM Parte al liv.8 CON la Roccia di Re: Poliwhirl evolve in POLITOAD
REM (Acqua, supporto curatore, passiva Piovischio). R: Rimbalzo / Ultimocanto.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/poliwag.json --level 8 --item king_rock
