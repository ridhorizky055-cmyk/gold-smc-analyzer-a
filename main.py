from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import os, sqlite3, json, urllib.request

app=FastAPI(title="GOLD SMC ANALYZER AI", version="0.1.0")
DB=os.path.join(os.path.dirname(__file__),"gold_smc.db")
def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY, side TEXT, entry REAL, sl REAL, tp REAL, qty REAL, status TEXT, pnl REAL DEFAULT 0, created TEXT)""")
    c.commit(); return c
class TradeIn(BaseModel):
    side:str; entry:float; sl:float; tp:float; qty:float=1
@app.get("/api/status")
def status():
    return {"app":"GOLD SMC ANALYZER AI","mode":"paper only","provider":os.getenv("GOLD_PROVIDER","Not configured"),"data_status":"not connected" if not os.getenv("GOLD_API_URL") else "provider configured","updated_at":None}
@app.get("/api/candles")
def candles():
    url=os.getenv("GOLD_API_URL")
    if not url: return {"symbol":"XAUUSD","source":"Demo data unavailable for live use","status":"WAIT","candles":[]}
    req=urllib.request.Request(url,headers={"Authorization":"Bearer "+os.getenv("GOLD_API_KEY","")})
    try:
        with urllib.request.urlopen(req,timeout=8) as r: raw=json.load(r)
        # Expected normalized schema: {"candles":[{"time":unix_seconds,"open":...,"high":...,"low":...,"close":...}]}
        cs=raw.get("candles",[])
        valid=[x for x in cs if all(k in x for k in ("time","open","high","low","close")) and x["high"]>=max(x["open"],x["close"]) and x["low"]<=min(x["open"],x["close"])]
        return {"symbol":"XAUUSD","source":os.getenv("GOLD_PROVIDER","Configured provider"),"status":"OK" if valid else "WAIT","candles":valid,"updated_at":datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"symbol":"XAUUSD","source":os.getenv("GOLD_PROVIDER","Configured provider"),"status":"WAIT","error":"Data unavailable or invalid","candles":[]}
@app.get("/api/analyze")
def analyze():
    data=candles()
    cs=data.get("candles",[])
    if len(cs)<20 or data["status"]!="OK":
        return {"signal":"WAIT","reason":"Data tidak tersedia/kurang; sinyal tidak dibuat.","checks":{"data_valid":False},"levels":None}
    closes=[x["close"] for x in cs[-20:]]
    highs=[x["high"] for x in cs[-20:]]; lows=[x["low"] for x in cs[-20:]]
    bullish=closes[-1]>closes[-5] and closes[-1]>sum(closes)/len(closes)
    bearish=closes[-1]<closes[-5] and closes[-1]<sum(closes)/len(closes)
    # Minimal illustrative rule, explicitly not a complete institutional SMC detector.
    sig="WAIT"; reason="Konfirmasi struktur sederhana belum terpenuhi."
    if bullish and not bearish: sig="BUY"; reason="Momentum/posisi close mendukung bullish; tunggu validasi SMC lengkap."
    if bearish and not bullish: sig="SELL"; reason="Momentum/posisi close mendukung bearish; tunggu validasi SMC lengkap."
    return {"signal":sig,"reason":reason,"checks":{"data_valid":True,"simple_momentum_bullish":bullish,"simple_momentum_bearish":bearish,"full_smc_confirmed":False},"levels":None,"note":"Sinyal indikatif prototipe. Entry/SL/TP tidak dibuat tanpa aturan invalidasi tervalidasi."}
@app.post("/api/trades")
def add_trade(t:TradeIn):
    if t.side not in ("BUY","SELL") or t.qty<=0: raise HTTPException(400,"Invalid trade")
    if (t.side=="BUY" and not t.sl<t.entry<t.tp) or (t.side=="SELL" and not t.tp<t.entry<t.sl): raise HTTPException(400,"Levels inconsistent")
    c=db(); c.execute("INSERT INTO trades(side,entry,sl,tp,qty,status,created) VALUES(?,?,?,?,?,'OPEN',?)",(t.side,t.entry,t.sl,t.tp,t.qty,datetime.now(timezone.utc).isoformat())); c.commit(); i=c.execute("SELECT last_insert_rowid()").fetchone()[0]; c.close()
    return {"id":i,"status":"OPEN","mode":"virtual"}
@app.get("/api/trades")
def trades():
    c=db(); rows=[dict(r) for r in c.execute("SELECT * FROM trades ORDER BY id DESC")]; c.close(); return rows
