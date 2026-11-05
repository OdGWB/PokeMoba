@echo off
REM Parte al liv.8 CON l'Augite Nera: Scyther evolve in KLEAVOR
REM (Coleottero/Roccia, passiva Asce di Pietra). R: Taglio d'Albero / Spaccaroccia.
cd /d "%~dp0"
python run_client.py --single --pokemon data/pokemon/scyther.json --level 8 --item black_augurite
