# 🛡️ NFT GARANT PRO — Automated Escrow Mini App

**NFT GARANT PRO** — это автоматизированный гарант-сервис для безопасных сделок с NFT-подарками в Telegram.

### 🛠 Технологии
* **Backend:** FastAPI (Python 3.10+)
* **Frontend:** HTML5/CSS3/JS (Telegram Mini App)
* **Database:** aiosqlite (Asynchronous SQLite)
* **Payments:** CryptoPay API

### 🔥 Уникальные фишки
* **Arbitration System:** В коде реализована роль Арбитра (ADMIN_ID: 8255489825), который может разрешать споры в реальном времени.
* **Smart Watchdog:** Если продавец не передает товар за 450 секунд, система автоматически возвращает деньги покупателю.
* **Anti-AFK Timer:** 5-минутный лимит на оплату после входа покупателя в комнату сделки.

---
**Note:** The interface is currently in Russian. Global English localization is planned if there is enough interest.
