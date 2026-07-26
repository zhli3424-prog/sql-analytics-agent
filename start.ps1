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
        $value = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes($Bytes))
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

docker compose -p sql-analytics-agent up --build

