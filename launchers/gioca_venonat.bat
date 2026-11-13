@echo off
REM VENONAT (Coleottero/Veleno): tiratore di logoramento a distanza. Scaglie
REM Velenose (attacchi base speciali a distanza, accumuli di veleno fino a 6),
REM Psicoraggio, Velenpolvere, Raffica. Al liv.8 Venomoth (Lentifume').
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/venonat.json
