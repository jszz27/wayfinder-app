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

.EXAMPLE
    .\scripts\db.ps1 -Open
    Opens the door and prints what to type into pgAdmin or any other
    client, then leaves it open. A graphical tool holds its connection
    for as long as you are looking, so it cannot be wrapped the way a
    psql session can. Close it yourself when you are done.

.EXAMPLE
    .\scripts\db.ps1 -Password
    Prints just the password and changes nothing. Cloud SQL Studio runs
    inside Google's network, so it needs no door opened -- only something
    to type into the password box.

.EXAMPLE
    .\scripts\db.ps1 -Close
    Closes the door again. This clears the allow-list completely, which
    is the posture the instance is meant to sit in.
#>
param(
    [string]$Query,
    [switch]$Open,
    [switch]$Close,
    [switch]$Password
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

if ($Password) {
    Write-Host ""
    Write-Host "  Database  $Database"
    Write-Host "  Username  $DbUser"
    Write-Host "  Password  $env:PGPASSWORD"
    Write-Host ""
    Write-Host "Nothing was opened. This is for Cloud SQL Studio in the console." -ForegroundColor DarkGray
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    return
}

if ($Close) {
    & $Gcloud sql instances patch $Instance --clear-authorized-networks --quiet | Out-Null
    Write-Host "Closed. Nothing on the internet can reach the database." -ForegroundColor Green
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    return
}

# Whatever is on the list now, so it can be put back exactly.
$before = (& $Gcloud sql instances describe $Instance `
    --format="value[delimiter=','](settings.ipConfiguration.authorizedNetworks[].value)").Trim()

$me = (Invoke-RestMethod -Uri "https://api.ipify.org").Trim()
$opened = if ($before) { "$before,$me/32" } else { "$me/32" }

Write-Host "Opening the database to $me for this session..." -ForegroundColor DarkGray
& $Gcloud sql instances patch $Instance --authorized-networks=$opened --quiet | Out-Null

if ($Open) {
    Write-Host ""
    Write-Host "  Host      $Host_"
    Write-Host "  Port      5432"
    Write-Host "  Database  $Database"
    Write-Host "  Username  $DbUser"
    Write-Host "  Password  $env:PGPASSWORD"
    Write-Host ""
    Write-Host "The database is OPEN to $me until you close it:" -ForegroundColor Yellow
    Write-Host "  .\scripts\db.ps1 -Close" -ForegroundColor Yellow
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    return
}

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
