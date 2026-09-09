[CmdletBinding()]
param(
    [string]$ContainerName = "tatra-v3-intervals-mcp",
    [string]$ImageName = "intervals-mcp-server:local",
    [int]$Port = 8000,
    [switch]$Rebuild,
    [switch]$Recreate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $repoRoot ".env"
$runtimeDir = Join-Path $repoRoot ".runtime"

function Test-McpPort {
    param([int]$TargetPort)

    try {
        return [bool](Test-NetConnection `
            -ComputerName "127.0.0.1" `
            -Port $TargetPort `
            -WarningAction SilentlyContinue `
            -InformationLevel Quiet)
    } catch {
        return $false
    }
}

if (-not $Rebuild -and -not $Recreate -and (Test-McpPort -TargetPort $Port)) {
    Write-Host "MCP jest już dostępny pod http://127.0.0.1:$Port/mcp; nic nie zmieniam."
    exit 0
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker nie jest dostępny w PATH. Uruchom Docker Desktop i zainstaluj polecenie docker."
}

if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw "Brak $envFile. Utwórz go przez: Copy-Item .env.example .env, a następnie uzupełnij API_KEY i ATHLETE_ID."
}

$envContents = Get-Content -LiteralPath $envFile -Raw
foreach ($requiredKey in @("API_KEY", "ATHLETE_ID")) {
    $match = [regex]::Match($envContents, "(?m)^\s*$requiredKey\s*=\s*(?<value>[^#\r\n]*)")
    $value = if ($match.Success) {
        $match.Groups["value"].Value.Trim().Trim('"').Trim("'")
    } else {
        ""
    }

    if ([string]::IsNullOrWhiteSpace($value) -or $value.StartsWith("<YOUR_")) {
        throw "$requiredKey nie jest uzupełniony w $envFile. Skrypt nie wypisuje wartości sekretów."
    }
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

docker image inspect $ImageName *> $null
$imageExists = $LASTEXITCODE -eq 0
if ($Rebuild -or -not $imageExists) {
    Write-Host "Buduję obraz $ImageName..."
    & docker build --tag $ImageName $repoRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Budowanie obrazu Docker nie powiodło się."
    }
}

docker container inspect $ContainerName *> $null
$containerExists = $LASTEXITCODE -eq 0

if ($containerExists -and $Recreate) {
    Write-Host "Usuwam istniejący kontener $ContainerName zgodnie z parametrem -Recreate..."
    & docker rm --force $ContainerName
    if ($LASTEXITCODE -ne 0) {
        throw "Nie udało się usunąć kontenera $ContainerName."
    }
    $containerExists = $false
}

if ($containerExists) {
    $runningState = (& docker inspect --format "{{.State.Running}}" $ContainerName 2>$null).Trim()
    if ($runningState -eq "true") {
        Write-Host "Kontener $ContainerName już działa; używam istniejącej instancji."
    } else {
        Write-Host "Uruchamiam istniejący kontener $ContainerName..."
        & docker start $ContainerName
        if ($LASTEXITCODE -ne 0) {
            throw "Nie udało się uruchomić kontenera $ContainerName."
        }
    }
} else {
    Write-Host "Uruchamiam jeden współdzielony kontener Streamable HTTP..."
    & docker run --detach `
        --name $ContainerName `
        --restart unless-stopped `
        --env-file $envFile `
        --env "MCP_TRANSPORT=streamable-http" `
        --env "FASTMCP_HOST=0.0.0.0" `
        --env "FASTMCP_PORT=$Port" `
        --publish "127.0.0.1:${Port}:$Port" `
        --volume "${runtimeDir}:/app/.runtime" `
        $ImageName `
        python -m intervals_mcp_server.server
    if ($LASTEXITCODE -ne 0) {
        throw "Nie udało się uruchomić kontenera $ContainerName."
    }
}

$deadline = [DateTime]::UtcNow.AddSeconds(30)
$portReady = Test-McpPort -TargetPort $Port
while ([DateTime]::UtcNow -lt $deadline) {
    $runningState = (& docker inspect --format "{{.State.Running}}" $ContainerName 2>$null).Trim()
    if ($runningState -ne "true") {
        break
    }

    $portReady = Test-McpPort -TargetPort $Port
    if ($portReady) {
        break
    }
    Start-Sleep -Milliseconds 500
}

if (-not $portReady) {
    Write-Host "Kontener nie otworzył portu $Port. Ostatnie logi:"
    & docker logs --tail 80 $ContainerName
    throw "MCP Streamable HTTP nie jest gotowy pod http://127.0.0.1:$Port/mcp."
}

Write-Host "MCP działa pod http://127.0.0.1:$Port/mcp"
Write-Host "Agenty TATRA_V3 powinny wskazywać ten URL w projektowym .codex/config.toml."
Write-Host "Po zmianie obrazu użyj: .\scripts\start-mcp.ps1 -Rebuild -Recreate"
