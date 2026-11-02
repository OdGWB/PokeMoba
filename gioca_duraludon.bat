@echo off
REM DURALUDON (Acciaio/Drago): Conduzione (pioggia), Cannonflash, Tuononda,
REM Codadrago. Al liv.8 evolve in Archaludon.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/duraludon.json
