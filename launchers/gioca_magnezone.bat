@echo off
REM MAGNEZONE (Elettro/Acciaio), gia' al liv.8.
REM R a scelta: Bombagnete / Campo Elettrico (rotella o Tab mentre si mira: + / -).
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/magnemite.json --level 8
