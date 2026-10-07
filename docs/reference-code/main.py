import json, os, re, time
from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import stripe
from . import ai, mail, ocr, security as sec
from .db import Analysis, ApiKey, Base, Payment, User, engine, get_db

FREE = int(os.getenv("FREE_CREDITS", "3"))
MAX_BYTES = int(os.getenv("MAX_PDF_MB", "15")) * 1024 * 1024
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
PACK = int(os.getenv("PACK_CREDITS", "20"))
SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")

Base.metadata.create_all(engine)
app = FastAPI(title="Analyse immobilière BE", version="0.2.0")

# ---------- auth ----------
class Cred(BaseModel):
    email: str
    password: str

class EmailIn(BaseModel):
    email: str

class TokenIn(BaseModel):
    token: str

class ResetIn(BaseModel):
    token: str
    password: str

_hits: dict[str, list[float]] = {}  # limiteur en mémoire (1 processus); Redis si plusieurs instances

def throttle(key: str, limit: int = 5, window: int = 900):
    t = time.time()
    q = [x for x in _hits.get(key, []) if t - x < window]
    _hits[key] = q
    if len(q) >= limit:
        raise HTTPException(429, "Trop de tentatives, réessayez plus tard")

def hit(key: str):
    _hits.setdefault(key, []).append(time.time())

def ip(request: Request) -> str:  # derrière un proxy, configurez uvicorn --proxy-headers
    return request.client.host if request.client else "?"

def current_user(request: Request, x_api_key: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if x_api_key:
        k = db.scalar(select(ApiKey).where(ApiKey.key_hash == sec.sha(x_api_key), ApiKey.revoked == False))  # noqa: E712
        if not k:
            raise HTTPException(401, "Clé API invalide")
        return db.get(User, k.user_id)
    uid = sec.read_token(request.cookies.get("session", ""))
    user = db.get(User, uid) if uid else None
    if not user:
        raise HTTPException(401, "Non connecté")
    return user

def set_session(resp: Response, uid: int):
    resp.set_cookie("session", sec.make_token(uid), httponly=True, samesite="lax", secure=SECURE, max_age=7 * 86400)

def send_verify(bg: BackgroundTasks, u: User):
    t = sec.make_purpose_token(u.id, "verify", 2 * 86400, u.email)
    bg.add_task(mail.send, u.email, "Confirmez votre adresse e-mail",
                f"Bonjour,\n\nConfirmez votre adresse en ouvrant ce lien (valable 48 h) :\n{BASE_URL}/?verify={t}\n\n"
                "Si vous n'êtes pas à l'origine de cette inscription, ignorez ce message.")

def check_password(p: str):
    if len(p) < 10:
        raise HTTPException(422, "Mot de passe: 10 caractères minimum")

@app.post("/auth/register")
def register(c: Cred, resp: Response, bg: BackgroundTasks, db: Session = Depends(get_db)):
    email = c.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 254:
        raise HTTPException(422, "E-mail invalide")
    check_password(c.password)
    u = User(email=email, pw_hash=sec.hash_pw(c.password), credits=FREE)
    db.add(u)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Un compte existe déjà avec cet e-mail")
    send_verify(bg, u)
    set_session(resp, u.id)
    return {"ok": True}

@app.post("/auth/login")
def login(c: Cred, request: Request, resp: Response, db: Session = Depends(get_db)):
    email = c.email.strip().lower()
    key = f"login:{ip(request)}:{email}"
    throttle(key)
    u = db.scalar(select(User).where(User.email == email))
    if not u or not sec.check_pw(c.password, u.pw_hash):
        hit(key)
        raise HTTPException(401, "Identifiants incorrects")
    set_session(resp, u.id)
    return {"ok": True}

@app.post("/auth/logout")
def logout(resp: Response):
    resp.delete_cookie("session")
    return {"ok": True}

@app.post("/auth/verify")
def verify(t: TokenIn, db: Session = Depends(get_db)):
    r = sec.read_purpose_token(t.token, "verify")
    u = db.get(User, r[0]) if r else None
    if not u or u.email != r[1]:
        raise HTTPException(400, "Lien invalide ou expiré")
    u.verified = True
    db.commit()
    return {"ok": True}

@app.post("/auth/resend")
def resend(bg: BackgroundTasks, u: User = Depends(current_user)):
    if not u.verified:
        throttle(f"resend:{u.id}", 3, 3600)
        hit(f"resend:{u.id}")
        send_verify(bg, u)
    return {"ok": True}

@app.post("/auth/forgot")
def forgot(c: EmailIn, request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    key = f"forgot:{ip(request)}"
    throttle(key)
    hit(key)
    u = db.scalar(select(User).where(User.email == c.email.strip().lower()))
    if u:  # même réponse que le compte existe ou non (pas d'énumération)
        t = sec.make_purpose_token(u.id, "reset", 3600, sec.sha(u.pw_hash)[:16])
        bg.add_task(mail.send, u.email, "Réinitialisation de votre mot de passe",
                    f"Bonjour,\n\nPour choisir un nouveau mot de passe (lien valable 1 h, usage unique) :\n{BASE_URL}/?reset={t}\n\n"
                    "Si vous n'avez rien demandé, ignorez ce message : votre mot de passe reste inchangé.")
    return {"ok": True}

@app.post("/auth/reset")
def reset(c: ResetIn, db: Session = Depends(get_db)):
    check_password(c.password)
    r = sec.read_purpose_token(c.token, "reset")
    u = db.get(User, r[0]) if r else None
    if not u or r[1] != sec.sha(u.pw_hash)[:16]:  # l'empreinte change après usage: lien à usage unique
        raise HTTPException(400, "Lien invalide ou expiré")
    u.pw_hash = sec.hash_pw(c.password)
    u.verified = True  # l'accès à la boîte mail est prouvé
    db.commit()
    return {"ok": True}

@app.get("/me")
def me(u: User = Depends(current_user)):
    return {"email": u.email, "credits": u.credits, "verified": u.verified}

@app.delete("/me")  # droit à l'effacement (RGPD); les paiements sont conservés pour la comptabilité
def delete_me(resp: Response, u: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(Analysis).where(Analysis.user_id == u.id))
    db.execute(delete(ApiKey).where(ApiKey.user_id == u.id))
    db.execute(delete(User).where(User.id == u.id))
    db.commit()
    resp.delete_cookie("session")
    return {"ok": True}

# ---------- clés API ----------
@app.get("/me/keys")
def list_keys(u: User = Depends(current_user), db: Session = Depends(get_db)):
    ks = db.scalars(select(ApiKey).where(ApiKey.user_id == u.id, ApiKey.revoked == False)).all()  # noqa: E712
    return [{"id": k.id, "prefix": k.prefix, "created": k.created.isoformat()} for k in ks]

@app.post("/me/keys")
def create_key(u: User = Depends(current_user), db: Session = Depends(get_db)):
    key, prefix, h = sec.new_api_key()
    db.add(ApiKey(user_id=u.id, prefix=prefix, key_hash=h))
    db.commit()
    return {"key": key, "note": "Copiez-la maintenant: elle ne sera plus affichée."}

@app.delete("/me/keys/{kid}")
def revoke_key(kid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(update(ApiKey).where(ApiKey.id == kid, ApiKey.user_id == u.id).values(revoked=True))
    db.commit()
    return {"ok": True}

# ---------- crédits ----------
def take(db: Session, uid: int, n: int):
    r = db.execute(update(User).where(User.id == uid, User.credits >= n).values(credits=User.credits - n))
    db.commit()
    if r.rowcount == 0:
        raise HTTPException(402, "Crédits insuffisants")

def give(db: Session, uid: int, n: int):
    db.execute(update(User).where(User.id == uid).values(credits=User.credits + n))
    db.commit()

# ---------- analyse ----------
def process(name: str, data: bytes) -> dict:
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Fichier trop volumineux")
    if not data.startswith(b"%PDF"):
        raise HTTPException(415, "PDF requis")
    text, used_ocr = ocr.extract_text(data)
    if len(text.strip()) < 80:
        raise HTTPException(422, "Texte illisible, même après OCR")
    doc_type = ai.classify(text)
    if doc_type == "autre":
        raise HTTPException(422, "Type non pris en charge (PEB, conformité électrique, extrait cadastral, attestation du sol)")
    return {"fichier": name, "type": doc_type, "ocr": used_ocr, "analyse": ai.analyze(doc_type, text)}

def run(db: Session, user: User, files: list[UploadFile]) -> dict:
    if not user.verified:
        raise HTTPException(403, "Confirmez d'abord votre adresse e-mail (lien envoyé à l'inscription).")
    if not 1 <= len(files) <= 6:
        raise HTTPException(400, "Entre 1 et 6 documents")
    items = [(f.filename or "document.pdf", f.file.read(MAX_BYTES + 1)) for f in files]
    take(db, user.id, len(items))  # 1 crédit par document, remboursé en cas d'échec
    docs = []
    for name, data in items:
        try:
            d = process(name, data)
            db.add(Analysis(user_id=user.id, filename=name, doc_type=d["type"], result=json.dumps(d["analyse"], ensure_ascii=False)))
            db.commit()
        except HTTPException as e:
            give(db, user.id, 1)
            d = {"fichier": name, "erreur": e.detail}
        except Exception:
            give(db, user.id, 1)
            d = {"fichier": name, "erreur": "Erreur interne d'analyse, crédit remboursé"}
        docs.append(d)
    ok = [d["analyse"] | {"type": d["type"]} for d in docs if "analyse" in d]
    cross = None
    if len(ok) > 1:
        try:
            cross = ai.cross_check(ok)
        except Exception:
            cross = None
    return {"documents": docs, "synthese_croisee": cross}

@app.post("/v1/dossier")
def dossier(files: list[UploadFile] = File(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    return run(db, u, files)

@app.post("/v1/analyze")
def analyze_one(file: UploadFile = File(...), u: User = Depends(current_user), db: Session = Depends(get_db)):
    return run(db, u, [file])["documents"][0]

@app.get("/me/history")
def history(u: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Analysis).where(Analysis.user_id == u.id).order_by(Analysis.id.desc()).limit(50)).all()
    return [{"id": r.id, "fichier": r.filename, "type": r.doc_type, "date": r.created.date().isoformat(), "analyse": json.loads(r.result)} for r in rows]

@app.delete("/me/history/{aid}")
def delete_analysis(aid: int, u: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(Analysis).where(Analysis.id == aid, Analysis.user_id == u.id))
    db.commit()
    return {"ok": True}

# ---------- facturation Stripe ----------
@app.post("/billing/checkout")
def checkout(u: User = Depends(current_user)):
    price = os.getenv("STRIPE_PRICE_ID")
    if not (stripe.api_key and price):
        raise HTTPException(503, "Paiement non configuré")
    s = stripe.checkout.Session.create(
        mode="payment", line_items=[{"price": price, "quantity": 1}],
        client_reference_id=str(u.id), customer_email=u.email,
        success_url=BASE_URL + "/?paid=1", cancel_url=BASE_URL + "/",
    )
    return {"url": s.url}

@app.post("/billing/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    try:
        ev = stripe.Webhook.construct_event(
            await request.body(), request.headers.get("stripe-signature", ""), os.getenv("STRIPE_WEBHOOK_SECRET", ""))
    except Exception:
        raise HTTPException(400, "Signature invalide")
    if ev["type"] in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        s = ev["data"]["object"]
        if s.get("payment_status") == "paid" and s.get("client_reference_id"):
            uid = int(s["client_reference_id"])
            db.add(Payment(session_id=s["id"], user_id=uid, credits=PACK))
            try:
                db.commit()
                give(db, uid, PACK)
            except IntegrityError:  # déjà traité
                db.rollback()
    return {"received": True}

@app.get("/health")
def health():
    return {"ok": True}

app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="web")
