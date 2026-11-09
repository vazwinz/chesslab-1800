; Instalador do AURA para Windows (NSIS 3). Gerado pelo build_windows.ps1 depois do PyInstaller:
;   makensis /DVERSION=0.4.0 desktop\installer.nsi
; Instala por usuário (sem precisar de administrador) em %LOCALAPPDATA%\Programs\AURA.
; Os dados de treino ficam em %LOCALAPPDATA%\AURA e são mantidos ao desinstalar, a não ser que
; a pessoa peça para apagar. Este arquivo é UTF-8 com BOM (o makensis precisa do BOM para os acentos).
Unicode true
!ifdef AMD64
  Target amd64-unicode  ; used for testing under 64-bit-only Wine
!endif
!include "MUI2.nsh"
!include "LogicLib.nsh"

!ifndef VERSION
  !define VERSION "0.4.0"
!endif
!ifndef SRCDIR
  !define SRCDIR "dist\AURA"
!endif
!define APP "AURA"
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP}"
!define MUTEX "Local\AURA-ChessLab1800"  ; criado pelo AURA enquanto está aberto (desktop/aura.py)

Name "${APP}"
OutFile "dist\AURA-Setup-${VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\${APP}"
InstallDirRegKey HKCU "Software\${APP}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "${APP} ${VERSION}"

!define MUI_ICON "aura.ico"
!define MUI_UNICON "aura.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Instalar o AURA ${VERSION}"
!define MUI_WELCOMEPAGE_TEXT "O AURA é um app de treino de xadrez para chegar aos 1800 no Chess.com.$\r$\n$\r$\nJá usa uma versão anterior? Pode instalar por cima: o seu progresso fica em outra pasta e continua lá. Antes de atualizar o banco de dados, o AURA guarda uma cópia de segurança.$\r$\n$\r$\nClique em Avançar para continuar."
!define MUI_FINISHPAGE_RUN "$INSTDIR\AURA.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o AURA agora"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE-NOTICE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=${LANG_PORTUGUESEBR} "ProductName" "${APP}"
VIAddVersionKey /LANG=${LANG_PORTUGUESEBR} "FileDescription" "Instalador do ${APP}, treino de xadrez"
VIAddVersionKey /LANG=${LANG_PORTUGUESEBR} "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_PORTUGUESEBR} "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_PORTUGUESEBR} "LegalCopyright" "GPL-3.0"

; Instalar ou desinstalar com o AURA aberto deixaria arquivos presos: pede para fechar antes.
!macro WAIT_FOR_AURA_CLOSED
  ${Do}
    System::Call 'kernel32::OpenMutexW(i 0x00100000, i 0, w "${MUTEX}") p .r0'
    ${If} $0 P= 0
      ${Break}
    ${EndIf}
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "O AURA está aberto.$\r$\n$\r$\nFeche a janela do AURA e clique em Repetir." /SD IDCANCEL IDRETRY +2
    Abort
  ${Loop}
!macroend

Function .onInit
  !insertmacro WAIT_FOR_AURA_CLOSED
FunctionEnd

Function un.onInit
  !insertmacro WAIT_FOR_AURA_CLOSED
FunctionEnd

Section "AURA (obrigatório)" SecApp
  SectionIn RO
  ; troca a versão anterior por inteiro (os dados ficam em outra pasta e não são tocados)
  RMDir /r "$INSTDIR\_internal"
  SetOutPath "$INSTDIR"
  File /r "${SRCDIR}\*.*"
  File "LICENSE-NOTICE.txt"
  CreateDirectory "$SMPROGRAMS\${APP}"
  Delete "$SMPROGRAMS\${APP}\Uninstall ${APP}.lnk"  ; atalho em inglês da 0.3.0
  CreateShortcut "$SMPROGRAMS\${APP}\${APP}.lnk" "$INSTDIR\AURA.exe" "" "$INSTDIR\AURA.exe" 0
  CreateShortcut "$SMPROGRAMS\${APP}\Desinstalar o ${APP}.lnk" "$INSTDIR\Uninstall.exe"
  ; mesmo nome da 0.3.0: substitui o desinstalador antigo pelo novo, que só apaga os arquivos do AURA
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "Software\${APP}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "AURA"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\AURA.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
SectionEnd

Section "Atalho na área de trabalho" SecDesktop
  CreateShortcut "$DESKTOP\${APP}.lnk" "$INSTDIR\AURA.exe" "" "$INSTDIR\AURA.exe" 0
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApp} "O programa AURA, com o Stockfish incluído."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Um atalho para abrir o AURA pela área de trabalho."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  Delete "$DESKTOP\${APP}.lnk"
  Delete "$SMPROGRAMS\${APP}\${APP}.lnk"
  Delete "$SMPROGRAMS\${APP}\Desinstalar o ${APP}.lnk"
  Delete "$SMPROGRAMS\${APP}\Uninstall ${APP}.lnk"
  RMDir "$SMPROGRAMS\${APP}"
  ; Só os arquivos do próprio AURA. Nunca "RMDir /r $INSTDIR": a pasta pode ter sido escolhida
  ; à mão (Documentos, Área de trabalho...) e ter outros arquivos.
  Delete "$INSTDIR\AURA.exe"
  Delete "$INSTDIR\LICENSE-NOTICE.txt"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"  ; só sai se ficou vazia
  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "Software\${APP}"
  ; Os dados de treino ficam, a não ser que a pessoa peça (no modo silencioso, ficam sempre).
  IfFileExists "$LOCALAPPDATA\${APP}\*.*" 0 done
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "Apagar também os seus dados de treino?$\r$\n$\r$\nProgresso, partidas importadas, puzzles baixados e configurações, na pasta:$\r$\n$LOCALAPPDATA\${APP}$\r$\n$\r$\nIsso não pode ser desfeito. Escolha Não para manter os dados e usar de novo se reinstalar." /SD IDNO IDNO done
    RMDir /r "$LOCALAPPDATA\${APP}"
  done:
SectionEnd
