@echo off
REM Parte gia' al liv.8: ARMAROUGE (Fuoco/Psico) con la passiva Guardia.
REM R a scelta: Armatura Fluttuante / Psichico.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/charcadet.json --level 8 --armature fausta
