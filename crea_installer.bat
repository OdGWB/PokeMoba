@echo off
REM Crea dist\PokeMoba-Setup.exe dall'exe gia' fatto con crea_exe.bat.
REM Serve Inno Setup 6 (https://jrsoftware.org/isinfo.php).
REM Le Release su GitHub lo creano da sole: questo serve solo per provarlo in casa.
cd /d "%~dp0"

if not exist "dist\PokeMoba.exe" (
    echo Manca dist\PokeMoba.exe: lancia prima crea_exe.bat.
    pause
    exit /b 1
)

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
    echo Inno Setup 6 non trovato. Installalo da https://jrsoftware.org/isinfo.php
    pause
    exit /b 1
)

"%ISCC%" installer\PokeMoba.iss || goto :errore
echo.
echo FATTO: %~dp0dist\PokeMoba-Setup.exe
pause
exit /b 0

:errore
echo.
echo ERRORE: creazione dell'installer fallita (vedi sopra).
pause
exit /b 1
