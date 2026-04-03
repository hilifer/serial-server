' Create desktop shortcut for 耀嵘光储充管理系统
Set WshShell = CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")

' Get install path (same folder as this script)
strScriptPath = oFSO.GetParentFolderName(WScript.ScriptFullName)

' Desktop path
strDesktop = WshShell.SpecialFolders("Desktop")

' Create shortcut
Set oShortcut = WshShell.CreateShortcut(strDesktop & "\耀嵘光储充管理系统.lnk")
oShortcut.TargetPath = strScriptPath & "\launch.bat"
oShortcut.WorkingDirectory = strScriptPath
oShortcut.Description = "耀嵘光储充管理系统 - 停车场监控 + 能源看板"
oShortcut.WindowStyle = 1
oShortcut.Save

' Also create Start Menu shortcut
strStartMenu = WshShell.SpecialFolders("Programs")
If Not oFSO.FolderExists(strStartMenu & "\耀嵘光储充") Then
    oFSO.CreateFolder(strStartMenu & "\耀嵘光储充")
End If
Set oShortcut2 = WshShell.CreateShortcut(strStartMenu & "\耀嵘光储充\耀嵘光储充管理系统.lnk")
oShortcut2.TargetPath = strScriptPath & "\launch.bat"
oShortcut2.WorkingDirectory = strScriptPath
oShortcut2.Description = "耀嵘光储充管理系统"
oShortcut2.WindowStyle = 1
oShortcut2.Save

WScript.Echo "桌面快捷方式已创建！"
