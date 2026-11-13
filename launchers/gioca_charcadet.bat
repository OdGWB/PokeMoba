@echo off
REM Parte al liv.1: CHARCADET (Fuoco) con la passiva Armature.
REM Danno subito dai Pokemon nemici -> Armatura Fausta -> Armarouge al liv.8;
REM danno inflitto ai Pokemon nemici -> Armatura Infausta -> Ceruledge.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/charcadet.json
