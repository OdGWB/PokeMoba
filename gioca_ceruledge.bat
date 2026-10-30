@echo off
REM Parte gia' al liv.8: CERULEDGE (Fuoco/Spettro) con la passiva Doppia Lama.
REM R a scelta: Lama dei Rancori / Ombrartigli.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/charcadet.json --level 8 --armature infausta
