JWT baseline results (2026-10-17T12:45:23+08:00)
- register /auth/register -> 201, status=pending (admin approval required)
- login /auth/login (form) -> 200, access_token(jwt) len=211, expires_in=1800
- GET /auth/me with JWT -> 200
- POST /auth/api-keys with JWT -> 201 (omh_... key issued)
- GET /auth/me with API key -> 401 (REJECTED, as required)
- POST /auth/api-keys with API key -> 401 (REJECTED)
- GET /auth/me no auth -> 401
