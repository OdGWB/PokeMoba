@echo off
REM ROOKIDEE (Volante, tank di supporto) dal liv.1: Corvisquire al liv.4,
REM Corviknight (Volante/Acciaio) al liv.8. Potenziamenti Q5/W6/E7, R al liv.8.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/rookidee.json --level 1
