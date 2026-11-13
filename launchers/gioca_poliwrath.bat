@echo off
REM Parte gia' al liv.8: senza Roccia di Re, Poliwhirl evolve in POLIWRATH
REM (Acqua/Lotta, combattente di prima linea, passiva Assorbacqua). R: Dinamipugno / Zuffa.
cd /d "%~dp0.."
python run_client.py --single --pokemon data/pokemon/poliwag.json --level 8
