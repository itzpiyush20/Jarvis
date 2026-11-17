Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = scriptDir

pythonPath = "C:\Users\itzpi\AppData\Local\Programs\Python\Python313\pythonw.exe"
If Not fso.FileExists(pythonPath) Then
    pythonPath = "pythonw.exe"
End If

WshShell.Run """" & pythonPath & """ main.py --all", 0, False
