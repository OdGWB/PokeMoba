@echo off
REM Parte al liv.8 CON la Metalcoperta: Scyther evolve in SCIZOR
REM (Coleottero/Acciaio, passiva Tecnico). R: Troppoforte / Chele d'Acciaio.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/scyther.json --level 8 --item metal_coat
