"""Authentication routes: register, login, logout."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..csrf import require_csrf
from ..security import (
    hash_password, new_csrf_token, new_session_token, token_hash, verify_password,
)

router = APIRouter()

MIN_PASSWORD = 8


def _render(request: Request, template: str, status_code: int = 200, **ctx):
    return request.app.state.templates.TemplateResponse(
        request, template, {"config": request.app.state.config, **ctx},
        status_code=status_code,
    )


def _set_session(request: Request, user_id: int) -> RedirectResponse:
    cfg = request.app.state.config
    store = request.app.state.store
    token = new_session_token()
    csrf = new_csrf_token()
    store.create_session(user_id, token_hash(token), csrf, cfg.session_ttl_seconds)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        "session", token,
        max_age=cfg.session_ttl_seconds,
        httponly=True, samesite="lax", path="/",
    )
    return resp


@router.get("/landing", response_class=HTMLResponse)
async def landing(request: Request):
    if request.state.user:
        return RedirectResponse("/", status_code=303)
    return _render(request, "landing.html", csrf=request.state.csrf, active_page="landing")


@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    if request.state.user:
        return RedirectResponse("/", status_code=303)
    return _render(request, "register.html", csrf=request.state.csrf, errors=[], values={}, active_page="register")


@router.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
    csrf_token: str = Form(""),
):
    require_csrf(request, csrf_token)
    store = request.app.state.store
    errors: list[str] = []
    name = name.strip()
    email = email.strip().lower()

    if not name:
        errors.append("Nama wajib diisi.")
    if not email or "@" not in email:
        errors.append("Email tidak valid.")
    if len(password) < MIN_PASSWORD:
        errors.append(f"Password minimal {MIN_PASSWORD} karakter.")
    if password != password_confirm:
        errors.append("Konfirmasi password tidak sama.")
    if not errors and store.get_user_by_email(email):
        errors.append("Email sudah terdaftar.")

    if errors:
        return _render(request, "register.html", status_code=400,
                       csrf=request.state.csrf, errors=errors,
                       values={"name": name, "email": email}, active_page="register")

    user_id = store.create_user(name, email, hash_password(password))
    return _set_session(request, user_id)


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if request.state.user:
        return RedirectResponse("/", status_code=303)
    return _render(request, "login.html", csrf=request.state.csrf, error=None, values={}, active_page="login")


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
):
    require_csrf(request, csrf_token)
    store = request.app.state.store
    throttle = request.app.state.throttle
    email = email.strip().lower()

    # Throttle by email. Message stays uniform: a blocked account is
    # indistinguishable from a wrong password apart from the retry hint.
    if throttle.is_blocked(email):
        return _render(request, "login.html", status_code=429,
                       csrf=request.state.csrf,
                       error="Terlalu banyak percobaan. Coba lagi beberapa menit lagi.",
                       values={"email": email}, active_page="login")

    user = store.get_user_by_email(email)
    # Uniform failure message: never reveal whether the email exists.
    if not user or not verify_password(password, user["password_hash"]):
        throttle.record_failure(email)
        return _render(request, "login.html", status_code=400,
                       csrf=request.state.csrf,
                       error="Email atau password salah.", values={"email": email}, active_page="login")

    throttle.reset(email)
    return _set_session(request, int(user["id"]))


@router.post("/logout")
async def logout(request: Request, csrf_token: str = Form("")):
    require_csrf(request, csrf_token)
    cookie = request.cookies.get("session")
    if cookie:
        request.app.state.store.delete_session(token_hash(cookie))
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("session", path="/")
    return resp
