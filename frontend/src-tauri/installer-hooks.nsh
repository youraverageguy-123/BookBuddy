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
!macroend

; Retain the installer with the portable application and its local library.
!macro NSIS_HOOK_POSTINSTALL
  ${If} "$EXEDIR" != "$INSTDIR"
    CopyFiles /SILENT "$EXEPATH" "$INSTDIR\$EXEFILE"
  ${EndIf}
!macroend
