import hashlib, hmac, os, secrets, time
import jwt

SECRET = os.environ["SECRET_KEY"]

def hash_pw(pw: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + ":" + h.hex()

def check_pw(pw: str, stored: str) -> bool:
    salt, h = stored.split(":")
    calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(calc.hex(), h)

def make_token(uid: int) -> str:
    return make_purpose_token(uid, "session", 7 * 86400)

def read_token(t: str):
    r = read_purpose_token(t, "session")
    return r[0] if r else None

def make_purpose_token(uid: int, purpose: str, ttl: int, extra: str = "") -> str:
    return jwt.encode({"sub": str(uid), "p": purpose, "x": extra, "exp": int(time.time()) + ttl}, SECRET, "HS256")

def read_purpose_token(t: str, purpose: str):
    try:
        d = jwt.decode(t, SECRET, algorithms=["HS256"])
        return (int(d["sub"]), d.get("x", "")) if d.get("p") == purpose else None
    except Exception:
        return None

def sha(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()

def new_api_key():
    k = "sk_live_" + secrets.token_urlsafe(32)
    return k, k[:12], sha(k)
