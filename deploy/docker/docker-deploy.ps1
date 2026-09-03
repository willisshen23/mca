param(
    [ValidateSet("up", "down", "restart", "logs", "status")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"
$DeployDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $DeployDir "..\.."))
$ComposeFile = Join-Path $DeployDir "docker-compose.yml"
$EnvFile = Join-Path $ProjectRoot "backend\.env"
$EnvExample = Join-Path $ProjectRoot "backend\.env.example"
$RuntimeData = Join-Path $DeployDir "runtime-data"
$ProjectName = "activity-analysis"

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Desktop is not running or Docker access is unavailable."
}

docker compose version *> $null
if ($LASTEXITCODE -eq 0) {
    $ComposeCommand = @("docker", "compose")
} else {
    $LegacyCompose = Get-Command docker-compose -ErrorAction SilentlyContinue
    if ($LegacyCompose) {
        docker-compose version *> $null
    }
    if ($LegacyCompose -and $LASTEXITCODE -eq 0) {
        $ComposeCommand = @("docker-compose")
    } else {
        throw "Docker Compose is unavailable (docker compose or docker-compose)."
    }
}

if (-not (Test-Path -LiteralPath $EnvFile)) {
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Host "Created config file: $EnvFile" -ForegroundColor Yellow
    Write-Host "Update the LLM and bank API endpoints for the target environment." -ForegroundColor Yellow
}

$EnvContent = [System.IO.File]::ReadAllText($EnvFile)
$UpdatedEnvContent = $EnvContent
$MockUrlReplacements = @{
    "http://host.docker.internal:8005/api2/campaigns/search" = "http://mock:8005/api2/campaigns/search"
    "http://host.docker.internal:8005/api2/templates" = "http://mock:8005/api2/templates"
    "http://host.docker.internal:8005/api2/component-values" = "http://mock:8005/api2/component-values"
    "http://host.docker.internal:8005/api2/dataservice/query/{trade_code}" = "http://mock:8005/api2/dataservice/query/{trade_code}"
    "http://localhost:8005/api2/campaigns/search" = "http://mock:8005/api2/campaigns/search"
    "http://localhost:8005/api2/templates" = "http://mock:8005/api2/templates"
    "http://localhost:8005/api2/component-values" = "http://mock:8005/api2/component-values"
    "http://localhost:8005/api2/dataservice/query/{trade_code}" = "http://mock:8005/api2/dataservice/query/{trade_code}"
}
foreach ($OldUrl in $MockUrlReplacements.Keys) {
    $UpdatedEnvContent = $UpdatedEnvContent.Replace($OldUrl, $MockUrlReplacements[$OldUrl])
}
if ($UpdatedEnvContent -ne $EnvContent) {
    $Utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($EnvFile, $UpdatedEnvContent, $Utf8WithoutBom)
    Write-Host "Updated legacy host Mock URLs to http://mock:8005" -ForegroundColor Yellow
}

# LLM API Key 密文（enc:v1:）主密钥预检
if ($UpdatedEnvContent -match "enc:v1:") {
    if ($UpdatedEnvContent -match "(?m)^LLM_MASTER_KEY=") {
        Write-Host "Warning: LLM_MASTER_KEY found inside backend\.env (same file as ciphertext). Move it to the host env instead." -ForegroundColor Yellow
    }
    if ([string]::IsNullOrEmpty($env:LLM_MASTER_KEY)) {
        throw "backend\.env contains enc:v1: ciphertext but the host env LLM_MASTER_KEY is not set.`nSet it first and retry, e.g.:`n    `$env:LLM_MASTER_KEY = '<hex64>'`nThe master key must be injected on the host (compose passes it via environment), not stored in backend\.env."
    }
}

New-Item -ItemType Directory -Force -Path $RuntimeData | Out-Null

$ComposeArgs = @("--env-file", $EnvFile, "-p", $ProjectName, "-f", $ComposeFile)

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    $ExitCode = 0
    Push-Location $DeployDir
    try {
        if ($ComposeCommand.Count -eq 2) {
            & $ComposeCommand[0] $ComposeCommand[1] @ComposeArgs @Arguments
        } else {
            & $ComposeCommand[0] @ComposeArgs @Arguments
        }
        $ExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($ExitCode -ne 0) {
        throw "Docker Compose failed with exit code $ExitCode."
    }
}

switch ($Action) {
    "up" {
        Write-Host "Compose command: $($ComposeCommand -join ' ')"
        Invoke-Compose up -d --build

        $PortLine = Get-Content -LiteralPath $EnvFile |
            Where-Object { $_ -match "^PORT=" } |
            Select-Object -Last 1
        $AppPort = if ($PortLine) {
            (($PortLine -split "=", 2)[1] -replace "['`"\s]", "")
        } else {
            "9111"
        }
        Write-Host ""
        Write-Host "Deployment completed: http://localhost:$AppPort" -ForegroundColor Green
        Write-Host "Status: .\deploy\docker\docker-deploy.ps1 status"
        Write-Host "Logs:   .\deploy\docker\docker-deploy.ps1 logs"
    }
    "down" {
        Invoke-Compose down
    }
    "restart" {
        Invoke-Compose restart
    }
    "logs" {
        Invoke-Compose logs -f --tail=200
    }
    "status" {
        Invoke-Compose ps
    }
}
