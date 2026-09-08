<#
.SYNOPSIS
    Rotates the deployed database password.

.DESCRIPTION
    Written down because it was done by hand once and the sequence is not
    obvious. Two details in it are the whole reason it should not be
    improvised a second time:

    Order. The secrets are written first, then the database user, then the
    services. Changing the user before the secrets would leave the running
    revisions holding a password that no longer works, for longer.

    Verification before retirement. The old secret versions are disabled
    only after the new password is proven to work, so a failure anywhere
    leaves a way back rather than two broken halves.

    The password is generated as bytes and never printed, and it is
    written with WriteAllBytes rather than a redirect: PowerShell would
    otherwise append a CRLF, which is exactly what made a correct password
    fail authentication the first time this was set up.

    There is a gap of roughly a minute between the database user changing
    and the new revisions serving, during which requests that touch the
    database will fail. At this size that is the honest trade; removing it
    would mean two database users and a longer dance.

.EXAMPLE
    .\scripts\rotate-db-password.ps1
#>
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$Project  = "project-9cf694a4-6c55-4005-aa1"
$Instance = "wayfinder-db"
$DbUser   = "wayfinder"
$Database = "wayfinder"
$Region   = "us-central1"
$Conn     = "${Project}:${Region}:${Instance}"
$RestUrl  = "https://backend-rest-139220777182.us-central1.run.app"
$WsUrl    = "https://backend-ws-139220777182.us-central1.run.app"

$Gcloud = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
if (-not (Test-Path $Gcloud)) {
    $found = Get-Command gcloud -ErrorAction SilentlyContinue
    if (-not $found) { throw "Could not find gcloud. Is the Google Cloud SDK installed?" }
    $Gcloud = $found.Source
}

$env:CLOUDSDK_AUTH_ACCESS_TOKEN = (& $Gcloud auth application-default print-access-token).Trim()
$env:CLOUDSDK_CORE_PROJECT = $Project

if (-not $Force) {
    Write-Host "This rotates the LIVE database password." -ForegroundColor Yellow
    Write-Host "Requests that touch the database will fail for about a minute." -ForegroundColor Yellow
    $answer = Read-Host "Type 'rotate' to go ahead"
    if ($answer -ne "rotate") { Write-Host "Nothing changed."; return }
}

# What is enabled now, so exactly these are retired at the end and nothing
# is assumed about the rest of the history.
$oldPasswordVersions = (& $Gcloud secrets versions list wayfinder-db-password `
    --filter="state=ENABLED" --format="value(name)")
$oldUrlVersions = (& $Gcloud secrets versions list wayfinder-database-url `
    --filter="state=ENABLED" --format="value(name)")

$pwFile  = Join-Path $env:TEMP "wayfinder-pw-$([guid]::NewGuid()).tmp"
$urlFile = Join-Path $env:TEMP "wayfinder-url-$([guid]::NewGuid()).tmp"

try {
    # 64 characters, so every byte value maps onto the alphabet evenly and
    # the choice carries no bias.
    $alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    $bytes = New-Object byte[] 43
    ([System.Security.Cryptography.RandomNumberGenerator]::Create()).GetBytes($bytes)
    $password = -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })

    # Exact bytes. A trailing newline here is a password that does not work.
    [System.IO.File]::WriteAllBytes($pwFile, [System.Text.Encoding]::UTF8.GetBytes($password))
    $escaped = [System.Uri]::EscapeDataString($password)
    $url = "postgresql+asyncpg://${DbUser}:${escaped}@/${Database}?host=/cloudsql/${Conn}"
    [System.IO.File]::WriteAllBytes($urlFile, [System.Text.Encoding]::UTF8.GetBytes($url))
    Write-Host "1/6  Generated a new password. It is not printed anywhere." -ForegroundColor DarkGray

    & $Gcloud secrets versions add wayfinder-db-password --data-file=$pwFile | Out-Null
    & $Gcloud secrets versions add wayfinder-database-url --data-file=$urlFile | Out-Null
    Write-Host "2/6  Stored both new secret versions." -ForegroundColor DarkGray

    & $Gcloud sql users set-password $DbUser --instance=$Instance --password=$password --quiet | Out-Null
    Write-Host "3/6  Changed the database user. The old password is now dead." -ForegroundColor DarkGray

    foreach ($service in @("backend-rest", "backend-ws")) {
        & $Gcloud run services update $service --region=$Region `
            --update-secrets="DATABASE_URL=wayfinder-database-url:latest" --quiet | Out-Null
        Write-Host "4/6  Redeployed $service." -ForegroundColor DarkGray
    }

    # A bogus login is the useful check: it reads the users table and
    # answers 401. A database it cannot reach answers 500 instead, so the
    # status code tells "working" apart from "up but blind".
    #
    # example.com, not example.invalid. A reserved TLD is refused by
    # email-validator before the request reaches the database at all, so
    # the first version of this check reported 422 and failed a rotation
    # that had in fact worked. The address still belongs to nobody --
    # example.com is reserved for exactly this -- so no account can exist
    # at it and the answer is always 401.
    $body = '{"email":"rotation-check@example.com","password":"not a real password"}'
    $login = try {
        (Invoke-WebRequest -Uri "$RestUrl/api/auth/login" -Method Post -Body $body `
            -ContentType "application/json" -UseBasicParsing).StatusCode.ToString()
    } catch { $_.Exception.Response.StatusCode.value__.ToString() }

    $restHealth = (Invoke-WebRequest -Uri "$RestUrl/health" -UseBasicParsing).StatusCode
    $wsHealth   = (Invoke-WebRequest -Uri "$WsUrl/health" -UseBasicParsing).StatusCode

    Write-Host "5/6  REST $restHealth, WebSocket $wsHealth, login $login" -ForegroundColor DarkGray
    if ($login -ne "401" -or $restHealth -ne 200 -or $wsHealth -ne 200) {
        throw "The new password did not verify. The old secret versions are still enabled, so nothing is lost -- read the Cloud Run logs before retrying."
    }

    foreach ($version in $oldPasswordVersions) {
        & $Gcloud secrets versions disable $version --secret=wayfinder-db-password --quiet | Out-Null
    }
    foreach ($version in $oldUrlVersions) {
        & $Gcloud secrets versions disable $version --secret=wayfinder-database-url --quiet | Out-Null
    }
    Write-Host "6/6  Retired the previous secret versions." -ForegroundColor DarkGray
    Write-Host "Rotated." -ForegroundColor Green
}
finally {
    # The password exists on this machine only for as long as gcloud needs
    # to read it.
    Remove-Item $pwFile, $urlFile -ErrorAction SilentlyContinue
}
