@echo off
setlocal
set "APP=%~dp0"
set "PYTHON=python"

if /i "%~1"=="--executar" goto atualizar
if not exist "%USERPROFILE%\.streamlit\secrets.toml" (
    echo Configure primeiro o arquivo .streamlit\secrets.toml no seu perfil.
    pause
    exit /b 1
)
call "%~f0" --executar
if errorlevel 1 (
    echo A carga falhou. Consulte "%APP%\atualizacao-leads.log".
    pause
    exit /b 1
)
set "LEADS_BATCH=%~f0"
powershell.exe -NoProfile -Command "$q = [char]34; $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/d /s /c ' + $q + $q + $env:LEADS_BATCH + $q + ' --executar' + $q); $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 8am; $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable; Register-ScheduledTask -TaskName 'Direcional - Atualizar base de leads' -Action $action -Trigger $trigger -Settings $settings -Force -ErrorAction Stop | Out-Null"
if errorlevel 1 (
    echo A carga foi concluida, mas a tarefa semanal nao foi registrada.
    pause
    exit /b 1
)
echo Base atualizada. Proxima execucao agendada para segunda-feira, as 08:00.
pause
exit /b 0

:atualizar
cd /d "%APP%" || exit /b 1
"%PYTHON%" atualizar_base.py >> "%APP%\atualizacao-leads.log" 2>&1
exit /b %errorlevel%
