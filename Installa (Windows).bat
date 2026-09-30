@echo off
rem Installa Stratigrafia 3D in un ambiente Python dedicato (cartella .venv).
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python non trovato.
  echo Installa Python 3.12 da https://www.python.org/downloads/ ^(spunta "Add python.exe to PATH"^) e rilancia questo file.
  pause
  exit /b 1
)
rem preferisce Python 3.12 o 3.13 (librerie piu' collaudate); altrimenti la versione predefinita
set PYV=-3
py -3.13 -c "import sys" >nul 2>nul && set PYV=-3.13
py -3.12 -c "import sys" >nul 2>nul && set PYV=-3.12
if not exist ".venv\Scripts\python.exe" (
  echo Creo l'ambiente Python ^(py %PYV%^)...
  py %PYV% -m venv .venv || goto errore
)
".venv\Scripts\python.exe" --version
echo Installo le librerie ^(qualche minuto la prima volta^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -e ".[demo]" || goto errore
echo Installo la finestra dell'app...
".venv\Scripts\python.exe" -m pip install "pywebview>=5" || echo Finestra non disponibile: l'app si aprira' nel browser.
echo.
echo Installazione completata. Avvia l'app con "Avvia Stratigrafia 3D.bat".
pause
exit /b 0
:errore
echo Installazione non riuscita. Copia il messaggio qui sopra e mandamelo.
pause
exit /b 1
