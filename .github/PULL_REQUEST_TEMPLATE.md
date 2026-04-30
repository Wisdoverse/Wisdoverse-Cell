## Summary

- 

## Verification

- [ ] `python -m ruff check agents/ shared/ skills/ tests/`
- [ ] `python -m pytest -q`
- [ ] `cd gateway && go test ./...`
- [ ] `cd gateway && govulncheck ./...`
- [ ] `cd frontend && npm ci && npm run lint && npm test && npm audit --omit=dev --audit-level=high && npm run build`
- [ ] Public hygiene checks pass

## Risk

- [ ] Security/auth behavior changed
- [ ] Database schema or migration changed
- [ ] Event schema or agent contract changed
- [ ] Deployment, Docker, or CI behavior changed

## Notes

- 
