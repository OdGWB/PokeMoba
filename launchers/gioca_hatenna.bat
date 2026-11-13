@echo off
REM HATENNA (Psico): Quiete (agita chi lancia mosse vicino), Confusione,
REM Incantavoce, Forza Lunare. Al liv.4 Hattrem, al liv.8 Hatterene.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/hatenna.json
