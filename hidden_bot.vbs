Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
strPath = FSO.GetParentFolderName(WScript.ScriptFullName) & "\start_bot.bat"
WshShell.Run chr(34) & strPath & chr(34), 0
Set WshShell = Nothing