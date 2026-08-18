# Contributing

## Development setup

1. Copy `.env.example` to `.env` and add a test API key only when live model calls are required.
2. Start the stack with `docker compose -p sql-analytics-agent up -d --build`.
3. Run the test suite before submitting a change.

```powershell
docker compose -p sql-analytics-agent run --rm api pytest -q -p no:cacheprovider
```

## Pull requests

- Keep changes focused and explain the user impact.
- Add or update a test for security rules, parsers, money calculations, or transaction behavior.
- Do not weaken SQL allowlists or database permissions to make a failing query pass.
- Do not commit `.env`, real business data, API keys, generated reports, or editor files.
- Update the README when startup commands, environment variables, API behavior, or security boundaries change.

Live 30-question evaluation calls a paid model API. State clearly whether it was run and attach only sanitized results.
