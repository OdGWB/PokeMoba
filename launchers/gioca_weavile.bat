@echo off
REM Parte gia' al liv.8: WEAVILE (Buio/Ghiaccio) con Arraffalesto.
REM R a scelta: Notte Fonda / Picchiaduro.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/sneasel.json --level 8 --oro minion
