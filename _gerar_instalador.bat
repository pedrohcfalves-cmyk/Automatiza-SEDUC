@echo off
chcp 65001 >nul
cd /d "%~dp0"
set LOG=%~dp0construir_log.txt
echo Gerando o instalador (versao e limpeza de cache vem do instalador\construir.py)... > "%LOG%"
python instalador\construir.py >> "%LOG%" 2>&1
set RESULTADO=%ERRORLEVEL%
echo EXIT=%RESULTADO% >> "%LOG%"
echo FIM >> "%LOG%"
if not "%RESULTADO%"=="0" (
  echo O build falhou. Veja construir_log.txt
  exit /b %RESULTADO%
)
echo Pronto. Veja construir_log.txt
exit /b 0
