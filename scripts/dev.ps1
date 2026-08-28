[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$frontendDirectory = Join-Path $repositoryRoot "frontend"
$backendHealthUrl = "http://127.0.0.1:8000/health"
$backendPort = 8000

function Write-Step {
    param([string]$Message)

    Write-Host ""
    Write-Host $Message -ForegroundColor Cyan
}

function Test-BackendHealth {
    try {
        $response = Invoke-RestMethod -Uri $backendHealthUrl -TimeoutSec 2
        return $response.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Test-TcpPortInUse {
    param(
        [string]$Address,
        [int]$Port
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connection = $client.ConnectAsync($Address, $Port)
        if (-not $connection.Wait(500)) {
            return $false
        }
        return $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Get-ComposeServiceState {
    param([string]$Service)

    $containerId = (& docker compose ps -q $Service 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($containerId)) {
        return "unavailable"
    }

    $state = (& docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $containerId 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($state)) {
        return "unavailable"
    }
    return $state
}

function Wait-ForInfrastructure {
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        $postgresState = Get-ComposeServiceState -Service "postgres"
        $redisState = Get-ComposeServiceState -Service "redis"
        if ($postgresState -eq "healthy" -and $redisState -in @("running", "healthy")) {
            return @{
                Postgres = $postgresState
                Redis = $redisState
            }
        }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "Infrastructure did not become ready within 60 seconds (PostgreSQL: $postgresState; Redis: $redisState). Inspect 'docker compose ps' and container logs, then retry."
}

function Start-DevelopmentWindow {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$Command,
        [string]$FailureMarker
    )

    $escapedTitle = $Title.Replace("'", "''")
    $escapedDirectory = $WorkingDirectory.Replace("'", "''")
    $escapedMarker = $FailureMarker.Replace("'", "''")
    $bootstrap = @"
`$Host.UI.RawUI.WindowTitle = '$escapedTitle'
Set-Location -LiteralPath '$escapedDirectory'
& $Command
`$processExitCode = `$LASTEXITCODE
[System.IO.File]::WriteAllText('$escapedMarker', [string]`$processExitCode)
Write-Host ''
Write-Host '$escapedTitle stopped with exit code ' -ForegroundColor Red -NoNewline
Write-Host `$processExitCode -ForegroundColor Red
"@
    $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($bootstrap))
    $powerShellExecutable = (Get-Process -Id $PID).Path

    Start-Process `
        -FilePath $powerShellExecutable `
        -ArgumentList @("-NoExit", "-EncodedCommand", $encodedCommand) `
        -WorkingDirectory $WorkingDirectory | Out-Null
}

function Find-SentinelFrontend {
    $normalizedFrontendPath = $frontendDirectory.Replace("/", "\").ToLowerInvariant()
    try {
        $viteProcesses = Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" |
            Where-Object {
                $commandLine = [string]$_.CommandLine
                $normalizedCommandLine = $commandLine.Replace("/", "\").ToLowerInvariant()
                $normalizedCommandLine.Contains($normalizedFrontendPath) -and
                    $normalizedCommandLine.Contains("vite")
            }

        foreach ($viteProcess in $viteProcesses) {
            $listeners = Get-NetTCPConnection `
                -State Listen `
                -OwningProcess $viteProcess.ProcessId `
                -ErrorAction SilentlyContinue
            foreach ($listener in $listeners) {
                $url = "http://127.0.0.1:$($listener.LocalPort)/"
                try {
                    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
                    if ($response.StatusCode -eq 200 -and $response.Content -match "<title>SentinelAI") {
                        return $url
                    }
                }
                catch {
                    continue
                }
            }
        }
    }
    catch {
        return $null
    }
    return $null
}

$originalLocation = Get-Location
try {
    Set-Location -LiteralPath $repositoryRoot

    Write-Host "SentinelAI Local Development" -ForegroundColor White
    Write-Host "----------------------------" -ForegroundColor DarkGray

    Write-Step "[1/5] Checking prerequisites"
    $prerequisites = @(
        @{ Name = "docker"; Failure = "Docker CLI was not found. Install Docker Desktop and retry." },
        @{ Name = "uv"; Failure = "uv was not found. Install uv and retry." },
        @{ Name = "node"; Failure = "Node.js was not found. Install Node.js and retry." },
        @{ Name = "npm"; Failure = "npm was not found. Install Node.js/npm and retry." }
    )
    foreach ($prerequisite in $prerequisites) {
        if ($null -eq (Get-Command $prerequisite.Name -ErrorAction SilentlyContinue)) {
            throw $prerequisite.Failure
        }
    }

    $dockerServerVersion = (& docker info --format "{{.ServerVersion}}" 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($dockerServerVersion)) {
        throw "Docker Desktop / Docker Engine is not running. Start it and retry."
    }
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose is unavailable. Install the Docker Compose plugin and retry."
    }
    Write-Host "      Docker: ready"
    Write-Host "      uv: ready"
    Write-Host "      Node/npm: ready"

    if (-not (Test-Path -LiteralPath (Join-Path $frontendDirectory "node_modules\vite\bin\vite.js"))) {
        throw "Frontend dependencies are missing. Run 'cd frontend' followed by 'npm ci', then retry."
    }

    Write-Step "[2/5] Starting infrastructure"
    $postgresState = Get-ComposeServiceState -Service "postgres"
    $redisState = Get-ComposeServiceState -Service "redis"
    if ($postgresState -ne "healthy" -or $redisState -notin @("running", "healthy")) {
        & docker compose up -d postgres redis
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose could not start the SentinelAI infrastructure. Inspect the Compose output and retry."
        }
    }
    else {
        Write-Host "      Compose: reusing running services"
    }
    $infrastructure = Wait-ForInfrastructure
    Write-Host "      PostgreSQL: $($infrastructure.Postgres)"
    Write-Host "      Redis: $($infrastructure.Redis)"

    Write-Step "[3/5] Checking database"
    & uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Alembic could not apply the committed migrations. Inspect the migration output and retry."
    }
    Write-Host "      Alembic: current"

    Write-Step "[4/5] Starting backend"
    Write-Host "      API: http://127.0.0.1:8000"
    if (Test-BackendHealth) {
        Write-Host "      Backend: already running and healthy"
    }
    else {
        if (Test-TcpPortInUse -Address "127.0.0.1" -Port $backendPort) {
            throw "Port 8000 is already in use, but SentinelAI did not respond successfully. Resolve the port conflict and retry."
        }

        $backendFailureMarker = Join-Path ([IO.Path]::GetTempPath()) "sentinelai-backend-$([guid]::NewGuid().ToString('N')).failed"
        Start-DevelopmentWindow `
            -Title "SentinelAI Backend" `
            -WorkingDirectory $repositoryRoot `
            -Command "uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000" `
            -FailureMarker $backendFailureMarker

        $backendDeadline = [DateTime]::UtcNow.AddSeconds(60)
        do {
            if (Test-BackendHealth) {
                break
            }
            if (Test-Path -LiteralPath $backendFailureMarker) {
                $backendExitCode = Get-Content -Raw -LiteralPath $backendFailureMarker
                throw "The backend exited before becoming healthy (exit code $backendExitCode). Inspect the SentinelAI Backend terminal."
            }
            Start-Sleep -Milliseconds 750
        } while ([DateTime]::UtcNow -lt $backendDeadline)

        if (-not (Test-BackendHealth)) {
            throw "The backend did not become healthy within 60 seconds at $backendHealthUrl. Inspect the SentinelAI Backend terminal."
        }
        Write-Host "      Backend: healthy"
    }

    Write-Step "[5/5] Starting dashboard"
    $existingFrontendUrl = Find-SentinelFrontend
    if ($null -ne $existingFrontendUrl) {
        Write-Host "      Frontend: already running at $existingFrontendUrl"
        Write-Host "      Opening the existing dashboard in the default browser"
        Start-Process -FilePath $existingFrontendUrl | Out-Null
    }
    else {
        $frontendFailureMarker = Join-Path ([IO.Path]::GetTempPath()) "sentinelai-frontend-$([guid]::NewGuid().ToString('N')).failed"
        Start-DevelopmentWindow `
            -Title "SentinelAI Frontend" `
            -WorkingDirectory $frontendDirectory `
            -Command "npm run dev" `
            -FailureMarker $frontendFailureMarker

        $frontendDeadline = [DateTime]::UtcNow.AddSeconds(30)
        $launchedFrontendUrl = $null
        do {
            if (Test-Path -LiteralPath $frontendFailureMarker) {
                $frontendExitCode = Get-Content -Raw -LiteralPath $frontendFailureMarker
                throw "The Vite frontend exited during startup (exit code $frontendExitCode). Inspect the SentinelAI Frontend terminal."
            }
            $launchedFrontendUrl = Find-SentinelFrontend
            if ($null -ne $launchedFrontendUrl) {
                break
            }
            Start-Sleep -Milliseconds 750
        } while ([DateTime]::UtcNow -lt $frontendDeadline)

        if ($null -eq $launchedFrontendUrl) {
            throw "The Vite frontend did not become available within 30 seconds. Inspect the SentinelAI Frontend terminal."
        }
        Write-Host "      Frontend: $launchedFrontendUrl"
        Write-Host "      Browser opened by Vite"
    }

    Write-Host ""
    Write-Host "SentinelAI development environment is ready." -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Set-Location -LiteralPath $originalLocation
}
