@echo off
chcp 65001 >nul
cd /d "%~dp0"
set LOG=%~dp0construir_log.txt
echo Gerando o instalador 3.8 (com a limpeza de cache)... > "%LOG%"
python instalador\construir.py >> "%LOG%" 2>&1
echo EXIT=%ERRORLEVEL% >> "%LOG%"
echo FIM >> "%LOG%"
