@echo off
rem Avvia subito una partita in locale con Snivy (vs bot).
rem Doppio-clic su questo file per giocare quando vuoi.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/snivy.json
