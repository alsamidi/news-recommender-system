# Web MVP — Security Notes

Scope: the web layer in `src/web/`. The frozen research API is unchanged.
Review date: 2026-10-20.

---

## 1. What is implemented

| Control | Implementation |
|---------|----------------|
| Password storage | `hashlib.scrypt`, n=2^14, r=8, p=1, 16-byte per-user salt, 32-byte key. Format `scrypt$n$r$p$salt$hash`. |
| Password verification | Re-derives with the stored parameters; `hmac.compare_digest`; returns False on malformed hashes. |
| Session token | `secrets.token_urlsafe(32)`. Only its SHA-256 is stored (`sessions.token_hash`). |
| Cookie flags | `HttpOnly`, `SameSite=Lax`, `path=/`. `Secure` is **not** set — local HTTP demo (see §4). |
| Session rotation | A new token is issued on every login; the previous one is not reused. |
| Session expiry | 7-day TTL; expired rows are deleted when read, not merely ignored. |
| CSRF (sessions) | Per-session token stored in `sessions.csrf_token`; checked in handlers. |
| CSRF (anonymous) | HMAC-SHA256 over (nonce, timestamp) with a per-process secret; bound to a `csrf_nonce` cookie; 2-hour TTL. The signed token is reused across GETs so a form held open does not go stale. |
| Login throttling | 5 failures per email per 15 minutes, in-memory; successful login clears the counter; blocked attempts return 429 with a generic message. |
| SQL injection | All statements parameterised. No f-strings or concatenation in SQL. |
| Authorization | Every query filtered by the session's `user_id`. `?user_id=` is ignored. |
| Enumeration | Login failure message is identical for unknown email and wrong password. |
| Logging | No passwords, emails, tokens, or CSRF values are logged. |
| Secrets at rest | Demo persona credentials come from env vars; `.env` is gitignored. |

## 2. Verified by probe (not just by reading code)

| Probe | Result |
|-------|--------|
| Forged session cookie: `abc`, empty, 200 chars, `../../etc/passwd`, `' OR 1=1--` | all redirected (303) |
| Path-based bypass: `//histori`, `/./histori`, `/histori/`, `/%68istori`, `/berita/../histori`, `/histori?x=1` | all redirected (303) |
| `/static/../app.py` | 404, no file disclosure |
| Session token rotation on login | new token; verified |
| CSRF with attacker-planted `csrf` cookie + matching form token | **blocked** after the fix (403) |
| CSRF with valid token replayed against a different nonce | 403 |
| CSRF with tampered signature | 403 |
| Valid token held across a clock tick (1.2 s) | 400, not 403 (regression fixed) |
| Login: 6th failure for one email in the window | 429 |
| Login: failures for one email do not block another | 400 for the other email |
| Login: success clears the counter | throttle not blocked |
| Persona failure path | 2 bounded API calls (warm, then history), no loop |

## 3. Known limitations

| Limitation | Impact | Note |
|------------|--------|------|
| Rate limiting is per-email **and** per-IP | — | Resolved. Per-IP uses the socket peer, never `X-Forwarded-For`. Budget is 30/15 min vs 5/15 min per email, because one address is not one person (campus NAT, office, mobile gateway). |
| Rate-limit state is in-memory | Resets on restart; not shared across workers | Single-process MVP. Multi-worker needs a shared store. |
| `Secure` cookie flag | Off by default; on with `WEB_SECURE_COOKIES=1` | Intentional: the local demo runs on plain HTTP and a `Secure` cookie would never be sent. Enable it behind TLS. |
| CSRF secret | Per-process random by default; set `WEB_CSRF_SECRET` to fix it | A fixed secret keeps anonymous form tokens valid across restarts and workers. |
| Session TTL is fixed, not sliding | Sessions expire mid-use after 7 days | Approved decision. |
| No account lockout / CAPTCHA | Same as rate limiting | Out of MVP scope. |
| No password strength beyond length ≥ 8 | Weak passwords accepted | Approved for MVP. |
| `interactions` grows without bound | Disk growth over time | Approved (no purge). Fine at demo scale. |

## 4. Deployment checklist before any non-local use

1. Serve over HTTPS and set `WEB_SECURE_COOKIES=1`. ✅ supported
2. Set a fixed `WEB_CSRF_SECRET`. ✅ supported
3. Per-IP login rate limiting. ✅ implemented (30 failures / 15 min per socket peer)
4. Set `WEB_DEMO_PERSONA_PASSWORD` to a non-guessable value, or skip the persona.
5. Back up `data/web.db` or accept it is disposable.

Items 1-3 were implemented after the first review; 4-5 remain deployment
choices and cannot be enforced from code.

**Behind a reverse proxy**, set the peer address at the proxy (or rate-limit
there). The app deliberately does not read `X-Forwarded-For`: that header is
caller-controlled, so trusting it would let an attacker pick a fresh key per
attempt and never be limited.

## 5. Deliberate non-findings

These were examined and are **not** defects:

- **Two API calls when a persona seed fails** — the design is warm → history →
  popular. The failure path performs at most two calls, verified.
- **CSRF validated in handlers rather than middleware** — reading the body in
  middleware consumes the stream, so the handler would receive empty fields.
- **The CSRF cookie is not a secret** — it is a nonce; the signature is what
  authenticates the request.
- **Scores are never rendered** — not a security issue, but it also means no
  internal score leaks to the client.
