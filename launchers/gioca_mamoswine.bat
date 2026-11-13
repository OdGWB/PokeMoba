@echo off
REM MAMOSWINE (Ghiaccio/Terra), gia' al liv.8.
REM R a scelta: Terremoto / Era Glaciale.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/swinub.json --level 8
