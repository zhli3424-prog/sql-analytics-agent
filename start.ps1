$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created .env. Add DEEPSEEK_API_KEY before asking questions." -ForegroundColor Yellow
}

docker compose -p sql-analytics-agent up --build

