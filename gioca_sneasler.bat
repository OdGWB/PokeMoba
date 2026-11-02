@echo off
REM Parte gia' al liv.8: SNEASLER (Lotta/Veleno) con Scalaroccia.
REM R a scelta: Agguato dalla Rupe / Sporcolancio.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/sneasel.json --level 8 --oro neutrali
