@echo off
REM SPIRITOMB (Spettro/Buio, supporto roamer stile Bard), dal liv.1: raccogli gli
REM spiriti verdi in giungla/fiume. Potenziamenti al liv.4, ultimate al liv.8.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/spiritomb.json --level 1
