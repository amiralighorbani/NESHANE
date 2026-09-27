@echo off
chcp 65001 >nul
REM ---------------------------------------------------------------------------
REM  نشانه — ساخت تصاویر فروشگاهی با یک کلیک
REM
REM  روی همین فایل دوبار کلیک کن. خودش سرور نشانه را بالا می‌آورد، تصاویر را
REM  می‌سازد، سرور را می‌بندد و گالری را در مرورگر باز می‌کند. اگر سرور از قبل
REM  بالا باشد، همان را استفاده می‌کند و به آن دست نمی‌زند.
REM
REM  پورت دیگری لازم داری؟   make-shots.bat 8030
REM ---------------------------------------------------------------------------

cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8020"

where python >nul 2>nul
if errorlevel 1 goto :nopython
if not exist "tools\make_store_shots.py" goto :nowhere

echo.
echo   == ساخت تصاویر فروشگاهی نشانه روی پورت %PORT% ...
echo      (این کار چند دقیقه طول می‌کشد)
echo.
python tools\make_store_shots.py --serve --port %PORT%
if errorlevel 1 goto :failed

echo.
echo   == تمام شد. تصاویر در پوشهٔ marketing\screenshots ساخته شدند.
start "" "marketing\gallery.html"
goto :end

:nopython
echo.
echo   [!] پایتون پیدا نشد. هنگام نصب، گزینهٔ "Add python.exe to PATH" را تیک بزن.
goto :end

:nowhere
echo.
echo   [!] این فایل باید کنار پوشه‌های app و tools باشد.
goto :end

:failed
echo.
echo   [!] ساخت تصاویر با خطا تمام شد؛ متن خطا بالا آمده است.

:end
echo.
pause
