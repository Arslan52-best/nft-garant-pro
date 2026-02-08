import os, logging, aiosqlite, uuid, httpx, time, asyncio
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from aiocryptopay import AioCryptoPay

logging.basicConfig(level=logging.INFO)
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- КОНФИГУРАЦИЯ ---
CP_TOKEN = "YOUR_CRYPTOPAY_TOKEN_HERE"
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
BOT_USERNAME = "nftgarant2_bot"
ADMIN_ID = 8255489825 
cryptopay = AioCryptoPay(token=CP_TOKEN)

async def init_db():
    async with aiosqlite.connect("escrow.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS deals (
            id TEXT PRIMARY KEY, seller_id INTEGER, buyer_id INTEGER, 
            nft_id TEXT, model TEXT, amount REAL, status TEXT, 
            invoice_id INTEGER, seller_name TEXT, buyer_name TEXT, 
            nft_url TEXT, seller_photo TEXT, buyer_photo TEXT,
            last_seller_pulse INTEGER, last_buyer_pulse INTEGER)""")
        
        # Добавляем колонки ВРЕМЕНИ, ЮЗЕРНЕЙМОВ и 🔥 ПУЛЬС АДМИНА
        new_cols = [
            'paid_at INTEGER', 'shipped_at INTEGER', 'created_at INTEGER', 
            'buyer_joined_at INTEGER', 'seller_username TEXT', 'buyer_username TEXT',
            'last_admin_pulse INTEGER' # <--- ТРЕТЬЕ МЕСТО
        ]
        for col_def in new_cols:
            try:
                col_name = col_def.split()[0]
                await db.execute(f"ALTER TABLE deals ADD COLUMN {col_name} {col_def.split()[1]}")
            except:
                pass 
        await db.commit()

async def notify_admin(text, deal_id=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    # 🔥 Добавляем кнопку для быстрого входа админа
    reply_markup = {}
    if deal_id:
        reply_markup = {
            "inline_keyboard": [[
                {"text": "🚀 ВОЙТИ В СДЕЛКУ", "url": f"https://t.me/{BOT_USERNAME}/app?startapp={deal_id}"}
            ]]
        }
        
    payload = {
        "chat_id": ADMIN_ID, 
        "text": text, 
        "parse_mode": "HTML",
        "reply_markup": reply_markup if deal_id else None
    }
    async with httpx.AsyncClient() as client:
        try: await client.post(url, json=payload)
        except: pass

# --- СТОРОЖЕВОЙ ПЕС ---
async def watchdog():
    while True:
        try:
            now = int(time.time())
            async with aiosqlite.connect("escrow.db") as db:
                
                # 1. АВТО-ОТМЕНА (5 минут на оплату ПОСЛЕ ВХОДА)
                await db.execute("""
                    UPDATE deals 
                    SET status = 'cancelled' 
                    WHERE status IN ('created', 'confirmed', 'waiting_payment') 
                    AND buyer_id IS NOT NULL 
                    AND buyer_joined_at IS NOT NULL
                    AND (? - buyer_joined_at) > 300
                """, (now,))
                
                # 2. АВТО-ВОЗВРАТ (7.5 минут на передачу)
                async with db.execute("SELECT id, amount, buyer_id FROM deals WHERE status='paid' AND paid_at IS NOT NULL AND (? - paid_at) > 450", (now,)) as cursor:
                    rows = await cursor.fetchall()
                    for r in rows:
                        deal_id, amount, b_id = r
                        if b_id:
                            try:
                                await cryptopay.transfer(user_id=b_id, asset='USDT', amount=amount, spend_id=f"auto_ref_{deal_id}")
                                await db.execute("UPDATE deals SET status='refunded' WHERE id=?", (deal_id,))
                                await notify_admin(f"🔙 <b>Авто-возврат (AFK):</b> #{deal_id}")
                            except Exception as e:
                                print(f"Err refund {deal_id}: {e}")

                # 3. АВТО-СПОР (6 минут на подтверждение)
                await db.execute("""
                    UPDATE deals 
                    SET status = 'disputed' 
                    WHERE status = 'shipped' 
                    AND shipped_at IS NOT NULL 
                    AND (? - shipped_at) > 360
                """, (now,))
                
                await db.commit()
        except Exception as e:
            print(f"Watchdog error: {e}")
            
        await asyncio.sleep(10)

@app.on_event("startup")
async def startup(): 
    await init_db()
    asyncio.create_task(watchdog())

@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open("index.html", "r", encoding="utf-8") as f: return f.read()

@app.get("/api/get_deal/{deal_id}")
async def get_deal(deal_id: str):
    async with aiosqlite.connect("escrow.db") as db:
        async with db.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)) as cursor:
            r = await cursor.fetchone()
            if not r: return {"status": "error"}
            
            deal_id = r[0]
            now = int(time.time())
            status = r[6]
            
            # Проверка оплаты
            if status == 'waiting_payment' and r[7]:
                try:
                    invs = await cryptopay.get_invoices(invoice_ids=str(r[7]))
                    if invs and invs[0].status == 'paid':
                        status = 'paid'
                        await db.execute("UPDATE deals SET status='paid', paid_at=? WHERE id=?", (now, deal_id))
                        await db.commit()
                except: pass
            
            # Безопасное извлечение (включая last_admin_pulse)
            paid_at = r[15] if len(r) > 15 else None
            shipped_at = r[16] if len(r) > 16 else None
            buyer_joined_at = r[18] if len(r) > 18 else None
            s_username = r[19] if len(r) > 19 else ""
            b_username = r[20] if len(r) > 20 else ""
            last_admin_pulse = r[21] if len(r) > 21 else 0

            return {
                "id": r[0], "seller_id": r[1], "buyer_id": r[2], "model": r[4], "amount": r[5], 
                "status": status, "seller_name": r[8], "buyer_name": r[9], "nft_url": r[10], 
                "seller_photo": r[11], "buyer_photo": r[12], 
                "seller_username": s_username, "buyer_username": b_username,
                "last_seller_pulse": r[13], 
                "buyer_joined_at": buyer_joined_at, 
                "paid_at": paid_at,
                "shipped_at": shipped_at,
                "s_online": (now - (r[13] or 0)) < 15, 
                "b_online": (now - (r[14] or 0)) < 15,
                "a_online": (now - (last_admin_pulse or 0)) < 15 # 🔥 АДМИН ОНЛАЙН?
            }

@app.post("/api/action/{deal_id}")
async def deal_action(deal_id: str, req: Request):
    body = await req.json()
    new_status = body.get('status')
    now = int(time.time())
    
    async with aiosqlite.connect("escrow.db") as db:
        async with db.execute("SELECT amount, seller_id, buyer_id, last_seller_pulse, status FROM deals WHERE id = ?", (deal_id,)) as cursor:
            deal = await cursor.fetchone()
            if not deal: return {"status": "error"}
            amount, s_id, b_id, last_pulse, current_status = deal

        try:
            if new_status == 'shipped' and current_status == 'paid':
                await db.execute("UPDATE deals SET status=?, shipped_at=? WHERE id=?", (new_status, now, deal_id))
                await db.commit()
                return {"status": "ok"}

            elif new_status == 'completed':
                # Админ может завершить из ЛЮБОГО статуса, если деньги уже там
                await cryptopay.transfer(user_id=s_id, asset='USDT', amount=amount, spend_id=f"pay_{deal_id}")
            
            elif new_status == 'refunded':
                if b_id: await cryptopay.transfer(user_id=b_id, asset='USDT', amount=amount, spend_id=f"ref_{deal_id}")

        except Exception as e:
            return {"status": "error", "message": f"Ошибка: {str(e)}"}

        await db.execute("UPDATE deals SET status=? WHERE id=?", (new_status, deal_id))
        await db.commit()

    await notify_admin(f"🔔 Статус #{deal_id}: <b>{new_status}</b>", deal_id)
    return {"status": "ok"}

@app.post("/api/pulse/{deal_id}")
async def deal_pulse(deal_id: str, req: Request):
    body = await req.json()
    user_id = body.get('id')
    username = body.get('username', '')
    now = int(time.time())
    
    async with aiosqlite.connect("escrow.db") as db:
        # 🔥 ПРОВЕРКА: ЕСЛИ ЭТО АДМИН
        if user_id == ADMIN_ID:
            await db.execute("UPDATE deals SET last_admin_pulse=? WHERE id=?", (now, deal_id))
            await db.commit()
            return {"status": "ok", "role": "admin"} # Возвращаем роль админа

        async with db.execute("SELECT seller_id, buyer_id, model, amount FROM deals WHERE id = ?", (deal_id,)) as cursor:
            deal = await cursor.fetchone()
            if not deal: return {"status": "error"}
            s_id, b_id, nft_name, amount = deal

        if user_id == s_id:
            await db.execute("UPDATE deals SET last_seller_pulse=? WHERE id=?", (now, deal_id))
        else:
            if b_id is None:
                # ВХОД ПОКУПАТЕЛЯ
                await db.execute("UPDATE deals SET buyer_id=?, buyer_name=?, buyer_photo=?, last_buyer_pulse=?, buyer_joined_at=?, buyer_username=? WHERE id=?", 
                                 (user_id, body.get('name'), body.get('photo'), now, now, username, deal_id))
                # Шлем ссылку админу
                await notify_admin(f"👤 <b>Покупатель зашел!</b>\n@{username}\n#{deal_id}", deal_id)
            elif b_id != user_id:
                return {"status": "occupied"}
            else:
                await db.execute("UPDATE deals SET last_buyer_pulse=? WHERE id=?", (now, deal_id))
        
        await db.commit()
    return {"status": "ok"}

@app.post("/api/create_deal")
async def create_deal(req: Request):
    body = await req.json()    
    try: price = float(body.get('price', 0))
    except: return {"status": "error"}
    
    nft_url = body.get('nft_url', '') 
    if price < 2.0: return {"status": "error", "message": "Минимум 2 USDT"}        
    
    deal_id = str(uuid.uuid4())[:8]
    nft_name = nft_url.split('/')[-1].replace('-', ' ') 
    now = int(time.time())

    async with aiosqlite.connect("escrow.db") as db:
        # Вставляем данные + last_admin_pulse (0)
        await db.execute("INSERT INTO deals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)", 
                         (deal_id, body.get('seller_id'), None, "NFT", nft_name, price, 
                          "created", None, body.get('seller_name'), None, nft_url, 
                          body.get('seller_photo'), None, now, 0, 
                          None, None, now, None, 
                          body.get('seller_username'), None)) 
        await db.commit() 
    
    return {"status": "ok", "share_url": f"https://t.me/{BOT_USERNAME}/app?startapp={deal_id}"}

@app.get("/api/my_deals/{user_id}")
async def my_deals(user_id: int):
    async with aiosqlite.connect("escrow.db") as db:
        async with db.execute("SELECT id, model, amount, status, seller_id, nft_url FROM deals WHERE seller_id = ? OR buyer_id = ? ORDER BY rowid DESC LIMIT 30", (user_id, user_id)) as cursor:
            rows = await cursor.fetchall()
            res = []
            for r in rows:
                role = "Продавец" if r[4] == user_id else "Покупатель"
                res.append({"id":r[0], "model":r[1], "amount":r[2], "status_code":r[3], "status_text":r[3], "role":role, "nft_url":r[5]})
            return {"deals": res}

@app.post("/api/pay_deal")
async def pay_deal(req: Request):
    body = await req.json()
    total = round(float(body['amount']) * 1.05, 2) 
    invoice = await cryptopay.create_invoice(asset='USDT', amount=total, description=f"NFT {body['model']}")
    async with aiosqlite.connect("escrow.db") as db:
        await db.execute("UPDATE deals SET status='waiting_payment', invoice_id=? WHERE id=?", (invoice.invoice_id, body.get('id')))
        await db.commit()
    return {"status": "ok", "pay_url": invoice.bot_invoice_url}