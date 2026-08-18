# Security Policy

## Scope

This repository is a portfolio-grade internal MVP. It is designed for local or trusted-network evaluation, not direct public internet exposure.

## Reporting a vulnerability

Please do not open a public issue for authentication bypasses, SQL validation bypasses, secret exposure, or database permission problems. Use GitHub private vulnerability reporting when available, or contact the repository owner privately.

Include the affected version, reproduction steps, expected impact, and a minimal proof of concept. Do not access data that does not belong to you.

## Deployment requirements

Before any non-local deployment:

- replace the demo password and disable `ALLOW_WEAK_LOCAL_PASSWORD`;
- rotate every API key or password that has appeared in a screenshot, chat, log, or Git history;
- put the service behind HTTPS and set `COOKIE_SECURE=true`;
- use a database account that can only `SELECT` approved analytics tables;
- review `ANALYTICS_ALLOWED_TABLES` and `config/business_glossary.md`;
- provide managed backups, log retention, monitoring, and an incident owner;
- replace the environment-variable login with SSO or another managed identity system.

LLM-generated SQL must remain untrusted. Do not remove AST validation, the read-only transaction, statement timeout, row limit, or database permission boundary.

## Secrets

`.env` is ignored by Git. Never commit real API keys, database passwords, session secrets, exported production data, or evaluation outputs containing sensitive questions.
