$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created .env. Add DEEPSEEK_API_KEY before asking questions." -ForegroundColor Yellow
}

function Set-RandomSecret {
    param(
        [string]$Name,
        [int]$Bytes
    )
    $path = (Resolve-Path -LiteralPath ".env").Path
    $content = [IO.File]::ReadAllText($path)
    $pattern = "(?m)^" + [regex]::Escape($Name) + "=.*$"
    $existing = [regex]::Match($content, $pattern)
    if (-not $existing.Success -or $existing.Value -match "=change-this-") {
        $buffer = New-Object byte[] $Bytes
        $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $generator.GetBytes($buffer)
        } finally {
            $generator.Dispose()
        }
        $value = [Convert]::ToBase64String($buffer)
        $line = "$Name=$value"
        if ($existing.Success) {
            $content = [regex]::Replace($content, $pattern, $line)
        } else {
            $content = $content.TrimEnd() + [Environment]::NewLine + $line + [Environment]::NewLine
        }
        [IO.File]::WriteAllText($path, $content, [Text.UTF8Encoding]::new($false))
        return $value
    }
    return $null
}

$initialPassword = Set-RandomSecret -Name "APP_PASSWORD" -Bytes 18
$null = Set-RandomSecret -Name "SESSION_SECRET" -Bytes 32
if ($initialPassword) {
    Write-Host "Initial login: analyst / $initialPassword" -ForegroundColor Yellow
    Write-Host "Save it in a password manager. It will not be printed again." -ForegroundColor Yellow
}

docker compose -p sql-analytics-agent up -d --build

Write-Host "Waiting for SQL Analytics Agent..." -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(90)
do {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8010/api/health" -TimeoutSec 3
        if ($health.status -eq "ok") {
            Write-Host "Service is ready: http://127.0.0.1:8010" -ForegroundColor Green
            Write-Host "The containers keep running after this window closes." -ForegroundColor Green
            return
        }
    } catch {
        Start-Sleep -Seconds 2
    }
} while ((Get-Date) -lt $deadline)

docker compose -p sql-analytics-agent logs --tail 80 api
throw "Service did not become healthy within 90 seconds."

