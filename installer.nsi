!define PRODUCT_NAME "ReClip"
!define PRODUCT_VERSION "1.1.0"
!define PRODUCT_PUBLISHER "Bugsfree Studio"
!define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\ReClip.exe"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

SetCompressor lzma

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "dist\ReClip-Setup.exe"
InstallDir "$LOCALAPPDATA\BugsfreeStudio\ReClip"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show

Section "MainSection" SEC01
  SetOutPath "$INSTDIR"
  SetOverwrite ifnewer
  File "dist\ReClip.exe"
  File "tools\ffmpeg.exe"
  CreateDirectory "$SMPROGRAMS\BugsfreeStudio\ReClip"
  CreateShortCut "$SMPROGRAMS\BugsfreeStudio\ReClip\ReClip.lnk" "$INSTDIR\ReClip.exe"
  CreateShortCut "$DESKTOP\ReClip.lnk" "$INSTDIR\ReClip.exe"
SectionEnd

Section -AdditionalIcons
  CreateShortCut "$SMPROGRAMS\BugsfreeStudio\ReClip\Uninstall.lnk" "$INSTDIR\uninst.exe"
SectionEnd

Section -Post
  WriteUninstaller "$INSTDIR\uninst.exe"
  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\ReClip.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninst.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
SectionEnd

Section Uninstall
  Delete "$INSTDIR\uninst.exe"
  Delete "$INSTDIR\ReClip.exe"
  Delete "$INSTDIR\ffmpeg.exe"
  Delete "$DESKTOP\ReClip.lnk"
  Delete "$SMPROGRAMS\BugsfreeStudio\ReClip\ReClip.lnk"
  Delete "$SMPROGRAMS\BugsfreeStudio\ReClip\Uninstall.lnk"
  RMDir "$SMPROGRAMS\BugsfreeStudio\ReClip"
  RMDir "$SMPROGRAMS\BugsfreeStudio"
  RMDir "$INSTDIR"
  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
  DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
SectionEnd
