"""Локальные аккаунты и сессии; разбор адресов не зависит от авторизации."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix='/auth', tags=['Account'])
DB_PATH = Path(os.environ.get('JANA_AUTH_DB', str(Path(__file__).resolve().parent.parent / 'data' / 'accounts.sqlite3')))
COOKIE = 'jana_session'
SESSION_TTL = 7 * 24 * 3600
ITERATIONS = 600_000
_attempts = defaultdict(list)
_lock = threading.Lock()
_DUMMY_SALT = secrets.token_hex(16)


@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires REAL NOT NULL)')
            yield db
    finally:
        db.close()


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=80)


def check_origin(request):
    # SameSite cookie + проверка Origin запрещают межсайтовые изменения сессии.
    origin = request.headers.get('origin')
    expected = f'{request.url.scheme}://{request.url.netloc}'
    if origin and origin.rstrip('/') != expected:
        raise HTTPException(403, 'origin_not_allowed')


def email_key(value):
    value = value.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise HTTPException(400, 'invalid_email')
    return value


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()


def rate_limit(request):
    key = request.client.host if request.client else 'local'
    now = time.monotonic()
    with _lock:
        recent = [t for t in _attempts[key] if t > now - 900]
        if len(recent) >= 20:
            raise HTTPException(429, 'too_many_attempts')
        _attempts[key] = recent + [now]


def start_session(db, user, request, response):
    old = request.cookies.get(COOKIE)
    if old:
        db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(old.encode()).hexdigest(),))
    token = secrets.token_urlsafe(32)
    db.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
    db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (hashlib.sha256(token.encode()).hexdigest(), user[0], time.time() + SESSION_TTL))
    response.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True, secure=request.url.scheme == 'https', samesite='strict', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {'user': {'id': user[0], 'name': user[1], 'email': user[2]}}


@router.post('/register', status_code=201)
def register(data: Registration, request: Request, response: Response):
    check_origin(request)
    rate_limit(request)
    email = email_key(data.email)
    name = data.name.strip()
    if not name:
        raise HTTPException(400, 'invalid_name')
    salt = secrets.token_hex(16)
    hashed = password_hash(data.password, salt)
    with database() as db:
        try:
            cursor = db.execute('INSERT INTO users (name,email,salt,password_hash) VALUES (?,?,?,?)', (name, email, salt, hashed))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'email_exists')
        return start_session(db, (cursor.lastrowid, name, email), request, response)


@router.post('/login')
def login(data: Credentials, request: Request, response: Response):
    check_origin(request)
    rate_limit(request)
    email = email_key(data.email)
    with database() as db:
        user = db.execute('SELECT id,name,email,salt,password_hash FROM users WHERE email=?', (email,)).fetchone()
        candidate = password_hash(data.password, user[3] if user else _DUMMY_SALT)
        if not user or not hmac.compare_digest(candidate, user[4]):
            raise HTTPException(401, 'invalid_credentials')
        return start_session(db, user, request, response)


@router.get('/me')
def me(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    token = request.cookies.get(COOKIE)
    if not token:
        return {'user': None}
    with database() as db:
        user = db.execute('SELECT u.id,u.name,u.email FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?', (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
    return {'user': {'id': user[0], 'name': user[1], 'email': user[2]} if user else None}


@router.post('/logout')
def logout(request: Request, response: Response):
    check_origin(request)
    token = request.cookies.get(COOKIE)
    if token:
        with database() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(COOKIE, path='/', httponly=True, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'
    return {'ok': True}
