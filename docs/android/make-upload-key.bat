@echo off
rem Makes the KeepWise Google Play upload key on THIS computer. The key never goes into the app folder or to anyone else.
rem It is saved in Documents\KeepWise-keys. Keep that folder backed up (a USB stick or your password manager): without it you
rem cannot publish updates until Google resets the key.
setlocal
set KEYDIR=%USERPROFILE%\Documents\KeepWise-keys
if not exist "%KEYDIR%" mkdir "%KEYDIR%"
where keytool >nul 2>nul
if errorlevel 1 (
  echo Java is not installed. Installing the free Temurin JDK 21 with winget...
  winget install --id EclipseAdoptium.Temurin.21.JDK -e --accept-source-agreements --accept-package-agreements
  echo.
  echo Java is installed. Close this window and double-click this file again.
  pause
  exit /b
)
if exist "%KEYDIR%\keepwise-upload.jks" (
  echo A key already exists in %KEYDIR%. Not making another one.
  pause
  exit /b
)
echo.
echo Choose a strong password (at least 12 characters). Type it twice when asked. It is not shown while you type.
echo Save it in your password manager now: you will paste it into GitHub in a minute.
echo.
keytool -genkeypair -v -storetype PKCS12 -keystore "%KEYDIR%\keepwise-upload.jks" -alias keepwise -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=KeepWise, O=KeepWise, C=US"
if errorlevel 1 ( echo Something went wrong. Nothing was saved. & pause & exit /b )
powershell -NoProfile -Command "[Convert]::ToBase64String([IO.File]::ReadAllBytes('%KEYDIR%\keepwise-upload.jks')) | Set-Content -NoNewline '%KEYDIR%\keepwise-upload-for-github.txt'"
echo.
echo Done. In %KEYDIR% you now have:
echo   keepwise-upload.jks              your upload key (back it up, never share it)
echo   keepwise-upload-for-github.txt   the same key as text, to paste into GitHub once, then delete this file
explorer "%KEYDIR%"
pause
