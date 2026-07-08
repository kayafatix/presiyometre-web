@echo off
echo ============================================
echo   Presiyometre Rapor - EXE Olusturma
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] Eski build temizleniyor...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo [2/3] EXE olusturuluyor...
pyinstaller --onefile --name "PresiyometreRapor" --add-data "templates;templates" --add-data "static;static" --console app.py

if %errorlevel% neq 0 (
    echo.
    echo HATA: Build basarisiz!
    pause
    exit /b 1
)

echo [3/3] Temizlik...
rmdir /s /q build
del /q PresiyometreRapor.spec 2>nul

echo.
echo ============================================
echo   BASARILI!
echo   EXE dosyasi: dist\PresiyometreRapor.exe
echo ============================================
echo.

:: EXE boyutunu göster
for %%A in (dist\PresiyometreRapor.exe) do echo   Boyut: %%~zA bytes (~%%~zA)
echo.
pause
