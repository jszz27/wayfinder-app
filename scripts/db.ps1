<#
.SYNOPSIS
    Opens a psql session against the deployed Wayfinder database.

.DESCRIPTION
    The Cloud SQL instance keeps an empty authorized-networks list, so
    nothing on the internet can reach it. Cloud Run does not need to: it
    connects over a private socket. Anyone looking at the data by hand
    does, which means four fiddly steps -- find gcloud, fetch the
    password, open the door, close it again. This does them.

    The door is closed in a finally block, so it closes even if psql
    crashes or you press Ctrl+C. Whatever was on the list before is put
    back rather than assumed empty.

    gcloud narrates both patches on stderr. That is left alone: silencing
    it would also silence a patch that failed, and a door that did not
    close is the one thing here worth hearing about.

    Authentication uses the Application Default Credentials already on
    this machine, so `gcloud auth login` is not required.

.EXAMPLE
    .\scripts\db.ps1
    Opens an interactive psql session.

.EXAMPLE
    .\scripts\db.ps1 -Query "select email from users;"
    Runs one statement and exits.
#>
param(
    [string]$Query
)

$ErrorActionPreference = "Stop"

$Project  = "project-9cf694a4-6c55-4005-aa1"
$Instance = "wayfinder-db"
$Database = "wayfinder"
$DbUser   = "wayfinder"

$Gcloud = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
if (-not (Test-Path $Gcloud)) {
    $found = Get-Command gcloud -ErrorAction SilentlyContinue
    if (-not $found) { throw "Could not find gcloud. Is the Google Cloud SDK installed?" }
    $Gcloud = $found.Source
}

$Psql = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" -ErrorAction SilentlyContinue |
        Select-Object -Last 1 -ExpandProperty FullName
if (-not $Psql) {
    $found = Get-Command psql -ErrorAction SilentlyContinue
    if (-not $found) { throw "Could not find psql. It ships with PostgreSQL." }
    $Psql = $found.Source
}

# Short-lived, and refreshed here rather than relying on a CLI login.
$env:CLOUDSDK_AUTH_ACCESS_TOKEN = (& $Gcloud auth application-default print-access-token).Trim()
$env:CLOUDSDK_CORE_PROJECT = $Project

Write-Host "Reading the password from Secret Manager..." -ForegroundColor DarkGray
$env:PGPASSWORD = (& $Gcloud secrets versions access latest --secret=wayfinder-db-password)
$Host_ = (& $Gcloud sql instances describe $Instance --format="value(ipAddresses[0].ipAddress)").Trim()

# Whatever is on the list now, so it can be put back exactly.
$before = (& $Gcloud sql instances describe $Instance `
    --format="value[delimiter=','](settings.ipConfiguration.authorizedNetworks[].value)").Trim()

$me = (Invoke-RestMethod -Uri "https://api.ipify.org").Trim()
$opened = if ($before) { "$before,$me/32" } else { "$me/32" }

Write-Host "Opening the database to $me for this session..." -ForegroundColor DarkGray
& $Gcloud sql instances patch $Instance --authorized-networks=$opened --quiet | Out-Null

try {
    Write-Host "Connected to the LIVE database. Changes here are real." -ForegroundColor Yellow
    if ($Query) {
        & $Psql -h $Host_ -U $DbUser -d $Database -c $Query
    } else {
        Write-Host "Type \dt to list tables, \q to quit." -ForegroundColor DarkGray
        & $Psql -h $Host_ -U $DbUser -d $Database
    }
}
finally {
    Write-Host "Closing the database again..." -ForegroundColor DarkGray
    if ($before) {
        & $Gcloud sql instances patch $Instance --authorized-networks=$before --quiet | Out-Null
    } else {
        & $Gcloud sql instances patch $Instance --clear-authorized-networks --quiet | Out-Null
    }
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Write-Host "Closed." -ForegroundColor DarkGray
}
