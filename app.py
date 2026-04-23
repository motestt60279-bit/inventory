from flask import Flask, render_template, request, jsonify, abort
from supabase import create_client, Client
from datetime import datetime
import pytz
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 唯讀分享 token（可自行修改成任意字串）
VIEW_TOKEN = os.getenv("VIEW_TOKEN", "view2025")

TW = pytz.timezone("Asia/Taipei")

def now_str():
    return datetime.now(TW).strftime("%Y/%m/%d %H:%M")

@app.route("/")
def index():
    return render_template("index.html", readonly=False)

@app.route("/view/<token>")
def view_readonly(token):
    if token != VIEW_TOKEN:
        abort(404)
    return render_template("index.html", readonly=True, vendor_id=None, vendor_name=None)

# ── 廠商專屬唯讀頁 ─────────────────────────────────────
@app.route("/view/vendor/<token>")
def view_vendor_readonly(token):
    res = supabase.table("vendors").select("id, name").eq("view_token", token).execute()
    if not res.data:
        abort(404)
    vendor = res.data[0]
    return render_template("index.html", readonly=True, vendor_id=vendor["id"], vendor_name=vendor["name"])

# ── 廠商 API ──────────────────────────────────────────
@app.route("/api/vendors", methods=["GET"])
def get_vendors():
    res = supabase.table("vendors").select("*").order("created_at").execute()
    vendors = res.data
    for v in vendors:
        prods = supabase.table("products").select("id, qty").eq("vendor_id", v["id"]).execute()
        v["product_count"] = len(prods.data)
        v["total_qty"] = sum(p["qty"] for p in prods.data)
    return jsonify(vendors)

@app.route("/api/vendors", methods=["POST"])
def add_vendor():
    body = request.json
    res = supabase.table("vendors").insert({"name": body["name"]}).execute()
    return jsonify(res.data[0])

@app.route("/api/vendors/<int:vid>", methods=["PUT"])
def update_vendor(vid):
    body = request.json
    res = supabase.table("vendors").update({"name": body["name"]}).eq("id", vid).execute()
    return jsonify(res.data[0])

@app.route("/api/vendors/<int:vid>", methods=["DELETE"])
def delete_vendor(vid):
    prods = supabase.table("products").select("id").eq("vendor_id", vid).execute()
    for p in prods.data:
        supabase.table("logs").delete().eq("product_id", p["id"]).execute()
    supabase.table("products").delete().eq("vendor_id", vid).execute()
    supabase.table("vendors").delete().eq("id", vid).execute()
    return jsonify({"ok": True})

# ── 廠商專屬 token 管理 ────────────────────────────────
@app.route("/api/vendors/<int:vid>/token", methods=["POST"])
def gen_vendor_token(vid):
    import secrets
    token = secrets.token_urlsafe(10)
    supabase.table("vendors").update({"view_token": token}).eq("id", vid).execute()
    return jsonify({"token": token})

# ── 品名 API ──────────────────────────────────────────
@app.route("/api/vendors/<int:vid>/products", methods=["GET"])
def get_products(vid):
    res = supabase.table("products").select("*").eq("vendor_id", vid).order("created_at").execute()
    return jsonify(res.data)

@app.route("/api/vendors/<int:vid>/products", methods=["POST"])
def add_product(vid):
    body = request.json
    qty = int(body.get("qty", 0))
    prod = supabase.table("products").insert({
        "vendor_id": vid,
        "name": body["name"],
        "qty": qty,
        "box_note": body.get("box_note", ""),
        "note": body.get("note", "")
    }).execute().data[0]
    if qty > 0:
        supabase.table("logs").insert({
            "product_id": prod["id"],
            "operation": "新增",
            "qty_change": qty,
            "note": body.get("note") or "初始入庫",
            "logged_at": now_str()
        }).execute()
    return jsonify(prod)

@app.route("/api/products/<int:pid>", methods=["PUT"])
def update_product(pid):
    body = request.json
    old = supabase.table("products").select("qty").eq("id", pid).execute().data[0]
    new_qty = int(body.get("qty", old["qty"]))
    diff = new_qty - old["qty"]
    supabase.table("products").update({
        "name": body["name"],
        "qty": new_qty,
        "box_note": body.get("box_note", ""),
        "note": body.get("note", "")
    }).eq("id", pid).execute()
    if diff != 0:
        op = "新增" if diff > 0 else "出貨"
        supabase.table("logs").insert({
            "product_id": pid,
            "operation": op,
            "qty_change": diff,
            "note": body.get("log_note", ""),
            "logged_at": now_str()
        }).execute()
    res = supabase.table("products").select("*").eq("id", pid).execute()
    return jsonify(res.data[0])

@app.route("/api/products/<int:pid>", methods=["DELETE"])
def delete_product(pid):
    supabase.table("logs").delete().eq("product_id", pid).execute()
    supabase.table("products").delete().eq("id", pid).execute()
    return jsonify({"ok": True})

# ── 庫存調整 API ──────────────────────────────────────
@app.route("/api/products/<int:pid>/adjust", methods=["POST"])
def adjust_qty(pid):
    body = request.json
    new_qty = int(body["qty"])
    note = body.get("note", "")
    old = supabase.table("products").select("qty").eq("id", pid).execute().data[0]
    diff = new_qty - old["qty"]
    op = "新增" if diff > 0 else ("出貨" if diff < 0 else "修改")
    supabase.table("products").update({"qty": new_qty}).eq("id", pid).execute()
    supabase.table("logs").insert({
        "product_id": pid,
        "operation": op,
        "qty_change": diff,
        "note": note,
        "logged_at": now_str()
    }).execute()
    return jsonify({"qty": new_qty})

# ── 紀錄 API ──────────────────────────────────────────
@app.route("/api/products/<int:pid>/logs", methods=["GET"])
def get_logs(pid):
    res = supabase.table("logs").select("*").eq("product_id", pid).order("logged_at", desc=True).execute()
    return jsonify(res.data)

@app.route("/api/logs/<int:lid>", methods=["PUT"])
def update_log(lid):
    body = request.json
    supabase.table("logs").update({
        "operation": body.get("operation"),
        "qty_change": int(body.get("qty_change", 0)),
        "note": body.get("note", ""),
        "logged_at": body.get("logged_at", now_str())
    }).eq("id", lid).execute()
    res = supabase.table("logs").select("*").eq("id", lid).execute()
    return jsonify(res.data[0])

@app.route("/api/logs/<int:lid>", methods=["DELETE"])
def delete_log(lid):
    supabase.table("logs").delete().eq("id", lid).execute()
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
