@echo off
REM Parte al liv.1: NOIBAT (Volante/Drago) con la passiva Ecolocalizzazione.
REM Attacchi base sonori (danno speciale); ogni terzo colpo un ping rivela i
REM nemici nascosti attorno al bersaglio. Evolve in Noivern al liv.8.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/noibat.json
