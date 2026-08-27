$ErrorActionPreference = "Stop"

$agent = Join-Path $PSScriptRoot "start_local_login.cmd"
$command = "`"$env:ComSpec`" /d /c start `"DouyinMind Login`" /min `"$agent`" `"%1`""
$base = "HKCU:\Software\Classes\douyinmind"

New-Item -Path $base -Force | Out-Null
New-ItemProperty -Path $base -Name '(Default)' -Value 'URL:DouyinMind Login Protocol' -PropertyType String -Force | Out-Null
New-ItemProperty -Path $base -Name 'URL Protocol' -Value '' -PropertyType String -Force | Out-Null
New-Item -Path "$base\shell\open\command" -Force | Out-Null
New-ItemProperty -Path "$base\shell\open\command" -Name '(Default)' -Value $command -PropertyType String -Force | Out-Null

Write-Host "DouyinMind 本机登录协议已安装。"
Write-Host "现在从网页点击扫码登录即可自动打开本机助手。"
