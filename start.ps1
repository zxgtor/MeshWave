$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$url = 'http://127.0.0.1:6188/'
try {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
    if ($response.Content -match 'Mesh Wave|FaceWrap Lite') { Start-Process $url; exit }
    throw 'Port 6188 is occupied by another application.'
} catch {
    if ($_.Exception.Message -like '*occupied*') { throw }
}
$localPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $localPython) { $pythonExe = $localPython }
else { $pythonExe = (Get-Command python).Source }
& $pythonExe -c 'import numpy, scipy, PIL, mediapipe, cv2'
if ($LASTEXITCODE -ne 0) { throw 'Install dependencies first: python -m pip install -r requirements.txt' }
$process = Start-Process -FilePath $pythonExe -ArgumentList 'server.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'server-error.log') -PassThru
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 250
    if ($process.HasExited) { throw 'Server exited; see server-error.log.' }
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1
        if ($response.Content -match 'Mesh Wave|FaceWrap Lite') { Start-Process $url; exit }
    } catch { }
}
throw 'Server did not become ready; see server-error.log.'
