import os
import sys
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from collectors.secure_credential_store import SecureCredentialStore

app = FastAPI(title="Algo Lab Settings UI")

# Allow local CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

class DhanCreds(BaseModel):
    client_id: str
    access_token: str

class AngelOneCreds(BaseModel):
    api_key: str
    client_code: str
    password: str
    totp_key: str

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), "r") as f:
        return f.read()

@app.get("/api/credentials")
def get_credentials_status():
    """Returns the status of credentials (Masked)."""
    store = SecureCredentialStore()
    creds = store.load_credentials()
    
    response = {}
    
    # Dhan
    dhan = creds.get("DHAN", {})
    response["DHAN"] = {
        "client_id": "***" + dhan.get("client_id", "")[-4:] if dhan.get("client_id") else "",
        "access_token": "********" if dhan.get("access_token") else "",
        "configured": bool(dhan.get("client_id") and dhan.get("access_token"))
    }
    
    # Angel One
    ao = creds.get("ANGEL_ONE", {})
    response["ANGEL_ONE"] = {
        "api_key": "********" if ao.get("api_key") else "",
        "client_code": "***" + ao.get("client_code", "")[-3:] if ao.get("client_code") else "",
        "password": "********" if ao.get("password") else "",
        "totp_key": "********" if ao.get("totp_key") else "",
        "configured": bool(ao.get("api_key") and ao.get("client_code") and ao.get("password") and ao.get("totp_key"))
    }
    
    return response

@app.post("/api/credentials/dhan")
def update_dhan(creds: DhanCreds):
    store = SecureCredentialStore()
    existing = store.load_credentials()
    existing["DHAN"] = {
        "client_id": creds.client_id,
        "access_token": creds.access_token
    }
    store.save_credentials(existing)
    return {"status": "success", "message": "Dhan credentials updated securely."}

@app.post("/api/credentials/angel_one")
def update_angel_one(creds: AngelOneCreds):
    store = SecureCredentialStore()
    existing = store.load_credentials()
    existing["ANGEL_ONE"] = {
        "api_key": creds.api_key,
        "client_code": creds.client_code,
        "password": creds.password,
        "totp_key": creds.totp_key
    }
    store.save_credentials(existing)
    return {"status": "success", "message": "Angel One credentials updated securely."}

if __name__ == "__main__":
    print("Starting Web UI on http://0.0.0.0:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)
