; Install into a self-contained BookBuddy folder beside the NSIS installer.
; If this is the retained installer copy inside BookBuddy, avoid nesting again.
!include "FileFunc.nsh"
!include "LogicLib.nsh"

!macro NSIS_HOOK_PREINSTALL
  ${GetFileName} "$EXEDIR" $R0
  ${If} $R0 == "BookBuddy"
    StrCpy $INSTDIR "$EXEDIR"
  ${Else}
    StrCpy $INSTDIR "$EXEDIR\BookBuddy"
  ${EndIf}
  ; The installer has already pointed its output at the previous $INSTDIR
  ; (the last install location, or %LOCALAPPDATA% on a new machine). Without
  ; this, the app is written there while the uninstaller, registry entry, and
  ; shortcuts all refer to the folder chosen above.
  SetOutPath "$INSTDIR"
!macroend

; Retain the installer with the portable application and its local library.
!macro NSIS_HOOK_POSTINSTALL
  ${If} "$EXEDIR" != "$INSTDIR"
    CopyFiles /SILENT "$EXEPATH" "$INSTDIR\$EXEFILE"
  ${EndIf}
!macroend
