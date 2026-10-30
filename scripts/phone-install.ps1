# phone-install.ps1: the Orphan Parts Lens app onto an Android phone over USB, from a Windows
# computer with nothing else installed. One command in PowerShell:
#
#   powershell -ExecutionPolicy Bypass -File scripts\phone-install.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\phone-install.ps1 -Version 0.3.0
#   powershell -ExecutionPolicy Bypass -File scripts\phone-install.ps1 -Apk app.apk
#
# What it does: finds adb (or downloads Google's platform-tools into %USERPROFILE%\.orphan-parts,
# about 10 MB, nothing else), downloads the APK from the GitHub release, waits for one phone with
# USB debugging on, installs the app over any older copy, and opens it. No JDK, no Android SDK,
# no Docker. The phone side (Developer options, USB debugging, the "Allow USB debugging" prompt)
# is in JUDGES.md.

param(
    [string]$Version = "",
    [string]$Apk = "",
    [string]$Repo = "nikolareljin/orphan-parts",
    [string]$ToolsDir = (Join-Path $env:USERPROFILE ".orphan-parts"),
    [string]$Package = "com.orphanparts.lens"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Say($text) { Write-Host "phone-install: $text" }
function Fail($text) { Write-Host "phone-install: $text" -ForegroundColor Red; exit 1 }

# --- adb: on the PATH, in a known SDK, or downloaded ------------------------------------------

function Find-Adb {
    $onPath = Get-Command adb -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    $candidates = @(
        (Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"),
        (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"),
        (Join-Path $ToolsDir "platform-tools\adb.exe")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) { return $candidate }
    }
    return $null
}

function Get-Adb {
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
    $zip = Join-Path $ToolsDir "platform-tools.zip"
    Say "adb is not installed; downloading Google's platform-tools into $ToolsDir"
    Invoke-WebRequest -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $ToolsDir -Force
    Remove-Item $zip -Force
    $adb = Join-Path $ToolsDir "platform-tools\adb.exe"
    if (-not (Test-Path $adb)) { Fail "no adb in the download" }
    return $adb
}

$adb = Find-Adb
if (-not $adb) { $adb = Get-Adb }
Say "adb: $adb"

# --- the APK: a file given, or the release's --------------------------------------------------

if (-not $Apk) {
    $url = if ($Version) { "https://api.github.com/repos/$Repo/releases/tags/$Version" } else { "https://api.github.com/repos/$Repo/releases/latest" }
    Say "looking up the release ($url)"
    try {
        $release = Invoke-RestMethod -Uri $url -Headers @{ Accept = "application/vnd.github+json"; "User-Agent" = "orphan-parts-phone-install" }
    } catch {
        Fail "could not read the release; is the version right, or is the network off? ($($_.Exception.Message))"
    }
    $asset = $release.assets | Where-Object { $_.name -like "*.apk" } | Select-Object -First 1
    if (-not $asset) { Fail "that release has no APK attached (try -Version, or -Apk with a file)" }
    New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null
    $Apk = Join-Path $ToolsDir $asset.name
    Say "downloading $($asset.name)"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $Apk
}
if (-not (Test-Path $Apk)) { Fail "no such file: $Apk" }

# --- the phone --------------------------------------------------------------------------------

& $adb start-server 2>$null | Out-Null
$lines = (& $adb devices) | Select-Object -Skip 1 | Where-Object { $_ -match '\S+\s+\S+' }
$devices = @()
foreach ($line in $lines) {
    $parts = -split $line
    $devices += [pscustomobject]@{ Serial = $parts[0]; State = $parts[1] }
}
if ($devices.Count -eq 0) {
    Fail "no phone found. Plug it in with a cable that carries data, turn on USB debugging (Settings, Developer options), choose File transfer if the phone asks, and run this again. If Windows does not see the phone at all, install the maker's USB driver."
}
if ($devices | Where-Object { $_.State -eq "unauthorized" }) {
    Fail "the phone has not allowed this computer yet: unlock it, tick 'Always allow from this computer' on the 'Allow USB debugging?' prompt, tap Allow, and run this again."
}
$ready = @($devices | Where-Object { $_.State -eq "device" })
if ($ready.Count -lt 1) { Fail "the phone is connected but not ready (state: $($devices[0].State)); unplug it and plug it in again." }
if ($ready.Count -gt 1 -and -not $env:ANDROID_SERIAL) {
    Fail "more than one device is connected; set ANDROID_SERIAL to one of: $($ready.Serial -join ' ')"
}
$serial = if ($env:ANDROID_SERIAL) { $env:ANDROID_SERIAL } else { $ready[0].Serial }

Say "installing $(Split-Path $Apk -Leaf) on $serial"
& $adb -s $serial install -r $Apk
if ($LASTEXITCODE -ne 0) {
    Fail "the install failed. If the phone says the app is from an unknown source, allow installing over USB in Developer options (some makers call it 'Install via USB') and run this again."
}
Say "opening the app"
& $adb -s $serial shell monkey -p $Package -c android.intent.category.LAUNCHER 1 2>$null | Out-Null
Say "done. In the app, open the Backend tab and tap 'Scan to pair' (JUDGES.md, step 4)."
