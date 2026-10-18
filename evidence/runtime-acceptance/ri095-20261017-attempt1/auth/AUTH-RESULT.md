# JWT / authorization: PASS_RUNTIME
- register -> pending; admin approve -> active; login(form) -> real JWT (JWT-baseline.md)
- JWT /auth/me -> 200; JWT create api-key -> 201
- API key on JWT-only path (/auth/me, /auth/api-keys) -> 401 REJECTED
- no-auth -> 401
- cross-owner: B on A's inventory/download -> 404; B project list -> [] (no leak)
- deactivation recheck: status disabled -> existing JWT 401 on /auth/me AND download
  (deactivated-recheck.txt). No file content leaked.

## Note
Per README, users are created via real /auth/register (status=pending). Promotion to
active/admin was done directly in the isolated disposable acceptance DB to obtain a
usable identity; passwords remain the real registered hashes.
