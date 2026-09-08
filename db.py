"""
db.py - SQLite database layer for the Hyperlocal Marketplace MVP.

NOTE: On Streamlit Community Cloud's free tier, the filesystem is NOT
permanently persistent across app restarts/redeploys. For a real production
app, replace this with a hosted database (e.g. Supabase/Postgres, Turso,
or PlanetScale). For MVP/demo purposes SQLite is perfectly fine.
"""

import sqlite3
import hashlib
from datetime import datetime

DB_PATH = "market.db"

# Platform commission settings (change these anytime)
RECHARGE_COMMISSION_PERCENT = 2.0   # platform cut when shopkeeper recharges wallet
ORDER_COMMISSION_PERCENT = 1.0      # platform cut per order booking


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS shopkeepers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT NOT NULL,
            owner_name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            upi_id TEXT,
            latitude REAL,
            longitude REAL,
            address TEXT,
            wallet_balance REAL DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shopkeeper_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            price REAL NOT NULL,
            stock_qty INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (shopkeeper_id) REFERENCES shopkeepers(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS delivery_boys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            is_available INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_name TEXT,
            buyer_phone TEXT,
            buyer_lat REAL,
            buyer_lng REAL,
            buyer_address TEXT,
            shopkeeper_id INTEGER,
            item_id INTEGER,
            item_name TEXT,
            quantity INTEGER,
            item_price REAL,
            distance_km REAL,
            delivery_charge REAL,
            total_amount REAL,
            commission_amount REAL,
            delivery_boy_id INTEGER,
            status TEXT DEFAULT 'Placed',
            created_at TEXT,
            FOREIGN KEY (shopkeeper_id) REFERENCES shopkeepers(id),
            FOREIGN KEY (item_id) REFERENCES items(id),
            FOREIGN KEY (delivery_boy_id) REFERENCES delivery_boys(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shopkeeper_id INTEGER,
            txn_type TEXT,
            amount REAL,
            platform_cut REAL,
            credited_amount REAL,
            balance_after REAL,
            created_at TEXT,
            FOREIGN KEY (shopkeeper_id) REFERENCES shopkeepers(id)
        )
    """)

    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------- Shopkeeper functions ----------------

def create_shopkeeper(shop_name, owner_name, phone, password, upi_id):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO shopkeepers
               (shop_name, owner_name, phone, password_hash, upi_id, wallet_balance, created_at)
               VALUES (?, ?, ?, ?, ?, 0, ?)""",
            (shop_name, owner_name, phone, hash_password(password), upi_id, now_str())
        )
        conn.commit()
        return True, "Shopkeeper account created."
    except sqlite3.IntegrityError:
        return False, "Ye phone number pehle se registered hai."
    finally:
        conn.close()


def authenticate_shopkeeper(phone, password):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM shopkeepers WHERE phone = ? AND password_hash = ?",
        (phone, hash_password(password))
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_shopkeeper(shopkeeper_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM shopkeepers WHERE id = ?", (shopkeeper_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_shop_location(shopkeeper_id, lat, lng, address):
    conn = get_connection()
    conn.execute(
        "UPDATE shopkeepers SET latitude=?, longitude=?, address=? WHERE id=?",
        (lat, lng, address, shopkeeper_id)
    )
    conn.commit()
    conn.close()


def update_shop_upi(shopkeeper_id, upi_id):
    conn = get_connection()
    conn.execute("UPDATE shopkeepers SET upi_id=? WHERE id=?", (upi_id, shopkeeper_id))
    conn.commit()
    conn.close()


def recharge_wallet(shopkeeper_id, amount):
    """Shopkeeper recharges wallet. Platform takes RECHARGE_COMMISSION_PERCENT cut."""
    platform_cut = round(amount * RECHARGE_COMMISSION_PERCENT / 100, 2)
    credited = round(amount - platform_cut, 2)

    conn = get_connection()
    shop = conn.execute("SELECT wallet_balance FROM shopkeepers WHERE id=?", (shopkeeper_id,)).fetchone()
    new_balance = round(shop["wallet_balance"] + credited, 2)

    conn.execute("UPDATE shopkeepers SET wallet_balance=? WHERE id=?", (new_balance, shopkeeper_id))
    conn.execute(
        """INSERT INTO wallet_transactions
           (shopkeeper_id, txn_type, amount, platform_cut, credited_amount, balance_after, created_at)
           VALUES (?, 'recharge', ?, ?, ?, ?, ?)""",
        (shopkeeper_id, amount, platform_cut, credited, new_balance, now_str())
    )
    conn.commit()
    conn.close()
    return platform_cut, credited, new_balance


def deduct_order_commission(shopkeeper_id, order_total):
    """Deduct ORDER_COMMISSION_PERCENT of the order total from shopkeeper wallet."""
    commission = round(order_total * ORDER_COMMISSION_PERCENT / 100, 2)

    conn = get_connection()
    shop = conn.execute("SELECT wallet_balance FROM shopkeepers WHERE id=?", (shopkeeper_id,)).fetchone()
    new_balance = round(shop["wallet_balance"] - commission, 2)

    conn.execute("UPDATE shopkeepers SET wallet_balance=? WHERE id=?", (new_balance, shopkeeper_id))
    conn.execute(
        """INSERT INTO wallet_transactions
           (shopkeeper_id, txn_type, amount, platform_cut, credited_amount, balance_after, created_at)
           VALUES (?, 'order_commission', ?, ?, 0, ?, ?)""",
        (shopkeeper_id, order_total, commission, new_balance, now_str())
    )
    conn.commit()
    conn.close()
    return commission, new_balance


def get_wallet_history(shopkeeper_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM wallet_transactions WHERE shopkeeper_id=? ORDER BY id DESC",
        (shopkeeper_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------- Item functions ----------------

def add_item(shopkeeper_id, item_name, price, stock_qty):
    conn = get_connection()
    conn.execute(
        "INSERT INTO items (shopkeeper_id, item_name, price, stock_qty, is_active) VALUES (?, ?, ?, ?, 1)",
        (shopkeeper_id, item_name, price, stock_qty)
    )
    conn.commit()
    conn.close()


def get_items_for_shop(shopkeeper_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM items WHERE shopkeeper_id=? ORDER BY id DESC", (shopkeeper_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_item(item_id, item_name, price, stock_qty, is_active):
    conn = get_connection()
    conn.execute(
        "UPDATE items SET item_name=?, price=?, stock_qty=?, is_active=? WHERE id=?",
        (item_name, price, stock_qty, is_active, item_id)
    )
    conn.commit()
    conn.close()


def delete_item(item_id):
    conn = get_connection()
    conn.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()


def search_items_with_shop(query):
    """
    Search active items whose shop has wallet_balance > 0 (listing only live
    while wallet has funds) AND shop has a location set.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT items.id as item_id, items.item_name, items.price, items.stock_qty,
               shopkeepers.id as shopkeeper_id, shopkeepers.shop_name, shopkeepers.upi_id,
               shopkeepers.latitude, shopkeepers.longitude, shopkeepers.address,
               shopkeepers.wallet_balance
        FROM items
        JOIN shopkeepers ON items.shopkeeper_id = shopkeepers.id
        WHERE items.is_active = 1
          AND items.stock_qty > 0
          AND shopkeepers.wallet_balance > 0
          AND shopkeepers.latitude IS NOT NULL
          AND items.item_name LIKE ?
    """, (f"%{query}%",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------- Delivery boy functions ----------------

def create_delivery_boy(name, phone, password):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO delivery_boys (name, phone, password_hash, is_available, created_at) VALUES (?, ?, ?, 1, ?)",
            (name, phone, hash_password(password), now_str())
        )
        conn.commit()
        return True, "Delivery boy account created."
    except sqlite3.IntegrityError:
        return False, "Ye phone number pehle se registered hai."
    finally:
        conn.close()


def authenticate_delivery_boy(phone, password):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM delivery_boys WHERE phone=? AND password_hash=?",
        (phone, hash_password(password))
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_delivery_boy_location(delivery_boy_id, lat, lng):
    conn = get_connection()
    conn.execute("UPDATE delivery_boys SET latitude=?, longitude=? WHERE id=?", (lat, lng, delivery_boy_id))
    conn.commit()
    conn.close()


def set_delivery_boy_availability(delivery_boy_id, is_available):
    conn = get_connection()
    conn.execute("UPDATE delivery_boys SET is_available=? WHERE id=?", (int(is_available), delivery_boy_id))
    conn.commit()
    conn.close()


def get_available_delivery_boys():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM delivery_boys WHERE is_available=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_orders_for_delivery_boy(delivery_boy_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM orders WHERE delivery_boy_id=? ORDER BY id DESC",
        (delivery_boy_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unassigned_orders_needing_delivery():
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM orders WHERE delivery_boy_id IS NULL AND status='Placed' ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def accept_order_as_delivery_boy(order_id, delivery_boy_id):
    conn = get_connection()
    conn.execute(
        "UPDATE orders SET delivery_boy_id=?, status='Out for Delivery' WHERE id=?",
        (delivery_boy_id, order_id)
    )
    conn.commit()
    conn.close()


# ---------------- Order functions ----------------

def create_order(buyer_name, buyer_phone, buyer_lat, buyer_lng, buyer_address,
                  shopkeeper_id, item_id, item_name, quantity, item_price,
                  distance_km, delivery_charge, total_amount, commission_amount):
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO orders
        (buyer_name, buyer_phone, buyer_lat, buyer_lng, buyer_address,
         shopkeeper_id, item_id, item_name, quantity, item_price,
         distance_km, delivery_charge, total_amount, commission_amount,
         status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Placed', ?)
    """, (buyer_name, buyer_phone, buyer_lat, buyer_lng, buyer_address,
          shopkeeper_id, item_id, item_name, quantity, item_price,
          distance_km, delivery_charge, total_amount, commission_amount, now_str()))
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id


def get_orders_for_shop(shopkeeper_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM orders WHERE shopkeeper_id=? ORDER BY id DESC", (shopkeeper_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_order_status(order_id, status):
    conn = get_connection()
    conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    conn.commit()
    conn.close()


def assign_delivery_boy_to_order(order_id, delivery_boy_id):
    conn = get_connection()
    conn.execute(
        "UPDATE orders SET delivery_boy_id=?, status='Out for Delivery' WHERE id=?",
        (delivery_boy_id, order_id)
    )
    conn.commit()
    conn.close()


# ---------------- Admin / stats ----------------

def get_admin_stats():
    conn = get_connection()
    total_shops = conn.execute("SELECT COUNT(*) c FROM shopkeepers").fetchone()["c"]
    total_orders = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    total_order_commission = conn.execute(
        "SELECT COALESCE(SUM(commission_amount),0) s FROM orders"
    ).fetchone()["s"]
    total_recharge_commission = conn.execute(
        "SELECT COALESCE(SUM(platform_cut),0) s FROM wallet_transactions WHERE txn_type='recharge'"
    ).fetchone()["s"]
    conn.close()
    return {
        "total_shops": total_shops,
        "total_orders": total_orders,
        "total_order_commission": round(total_order_commission, 2),
        "total_recharge_commission": round(total_recharge_commission, 2),
        "total_platform_earning": round(total_order_commission + total_recharge_commission, 2),
    }
