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
| Rate limiting is per-email only | An attacker can spread attempts across many emails | PRD §11 asks for "simple" limiting; per-IP limiting needs a proxy or shared store. |
| Rate-limit state is in-memory | Resets on restart; not shared across workers | Single-process MVP. Multi-worker needs a shared store. |
| `Secure` cookie flag absent | Cookie could travel over plain HTTP | Intentional for local HTTP demo. Must be enabled behind HTTPS. |
| Single-process CSRF secret | Restart invalidates outstanding anonymous form tokens | Acceptable: forms are short-lived. A multi-worker deploy would need a shared secret. |
| Session TTL is fixed, not sliding | Sessions expire mid-use after 7 days | Approved decision. |
| No account lockout / CAPTCHA | Same as rate limiting | Out of MVP scope. |
| No password strength beyond length ≥ 8 | Weak passwords accepted | Approved for MVP. |
| `interactions` grows without bound | Disk growth over time | Approved (no purge). Fine at demo scale. |

## 4. Deployment checklist before any non-local use

1. Serve over HTTPS and set `Secure` on the session and nonce cookies.
2. Set a fixed `csrf` secret from configuration instead of a per-process random value.
3. Add per-IP login rate limiting (per-email limiting already exists).
4. Set `WEB_DEMO_PERSONA_PASSWORD` to a non-guessable value, or skip the persona.
5. Back up `data/web.db` or accept it is disposable.

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
