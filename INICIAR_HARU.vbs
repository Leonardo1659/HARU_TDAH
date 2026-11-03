' Lanzador silencioso de 1 clic para Haru (Cero ventana negra de consola)
' Universidad Salesiana de Bolivia - Proyecto Integrador Asistente TDAH "Haru"

Dim fso, shell, carpeta, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = carpeta

On Error Resume Next
Err.Clear
shell.Run "pythonw """ & carpeta & "\haru.pyw""", 0, False
If Err.Number <> 0 Then
    Err.Clear
    shell.Run "pyw """ & carpeta & "\haru.pyw""", 0, False
    If Err.Number <> 0 Then
        MsgBox "No se encontró Python instalado en esta computadora." & vbCrLf & _
               "Instala Python 3.11+ marcando 'Add Python to PATH' y ejecuta INSTALAR_DEPENDENCIAS.bat.", _
               16, "Haru — Asistente Educativo TDAH"
    End If
End If

