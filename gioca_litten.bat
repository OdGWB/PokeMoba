@echo off
REM LITTEN (Fuoco) dal liv.1: Torracat al liv.4, Incineroar (Fuoco/Buio) al liv.8.
REM Lottatore da top lane: Bullo provoca, Corsa alle Corde usa i muri come corde del ring.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/litten.json
