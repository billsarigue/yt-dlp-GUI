; scripts/build-nsis.nsi
; Script NSIS para instalador customizado do yt-dlp-GUI
; (Tauri já gera NSIS automaticamente via tauri.conf.json;
;  use este script para personalizações avançadas)

!define APP_NAME "yt-dlp GUI"
!define APP_VERSION "2.1.0"
!define APP_PUBLISHER "yt-dlp-GUI Project"
!define APP_URL "https://github.com/billsarigue/yt-dlp-GUI"
!define APP_EXE "yt-dlp-GUI.exe"
!define INSTALL_DIR "$LOCALAPPDATA\yt-dlp-GUI"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "yt-dlp-GUI-Setup-${APP_VERSION}.exe"
InstallDir "${INSTALL_DIR}"
RequestExecutionLevel user   ; Instalação sem admin
Unicode True
SetCompressor /SOLID lzma

; Páginas do instalador
Page license
Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

; --- Seção principal ---
Section "Instalar ${APP_NAME}" SecMain
  SetOutPath "$INSTDIR"

  ; Copia todos os arquivos empacotados pelo Tauri
  File /r "src-tauri\target\release\bundle\nsis\*.*"

  ; Atalho no Menu Iniciar
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" \
    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0

  ; Atalho na Área de Trabalho (opcional)
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" \
    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0

  ; Entrada no Painel de Controle / Adicionar ou Remover Programas
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "URLInfoAbout" "${APP_URL}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" \
    "UninstallString" "$INSTDIR\uninstall.exe"

  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

; --- Desinstalação ---
Section "Uninstall"
  Delete "$INSTDIR\${APP_EXE}"
  Delete "$INSTDIR\uninstall.exe"
  RMDir /r "$INSTDIR"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
SectionEnd
