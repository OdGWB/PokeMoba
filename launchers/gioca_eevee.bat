@echo off
REM EEVEE (Normale), dal liv.4: in base scegli i potenziamenti Q (liv.5), W (liv.6)
REM ed E (liv.7); al liv.8 si evolve nella forma decisa dalla combinazione.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/eevee.json --level 4
