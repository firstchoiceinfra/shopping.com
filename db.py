"""
db.py - SQLite database layer for the Hyperlocal Marketplace MVP.

NOTE: On Streamlit Community Cloud's free tier, the filesystem is NOT
permanently persistent across app restarts/redeploys. For a real production
app, replace this with a hosted database (e.g. Supabase/Postgres, Turso).
"""

import sqlite3
import hashlib
from datetime import datetime, timedelta

DB_PATH = "market.db"

RECHARGE_COMMISSION_PERCENT = 2.0
ORDER_COMMISSION_PERCENT = 2.0
MIN_RECHARGE_AMOUNT = 100.0
LOW_BALANCE_THRESHOLD = 50.0
LOW_STOCK_THRESHOLD = 5

UNITS = ["piece", "gram", "kg", "ml", "litre"]

# ---------------------------------------------------------------------------
# Comprehensive Main Category -> Sub-category tree (A to Z coverage — from a
# needle to a TV to a bike). Shopkeeper picks Main + Sub; if their item
# doesn't fit anywhere, "Other" is always available at both levels so
# nothing is ever blocked.
# ---------------------------------------------------------------------------
CATEGORY_TREE = {
    "Electronics": ["Mobiles", "Tablets", "Laptops", "Computers & Accessories",
                     "Cameras", "Headphones & Earphones", "Speakers", "Power Banks",
                     "Chargers & Cables", "Smart Watches", "Printers", "Other Electronics"],
    "TV & Home Entertainment": ["Televisions", "Set-top Box", "Home Theatre", "Remote Controls",
                                 "Projectors", "Other"],
    "Home Appliances": ["Refrigerators", "Washing Machines", "Air Conditioners", "Coolers & Fans",
                         "Microwave & Ovens", "Water Purifiers", "Vacuum Cleaners", "Geysers",
                         "Irons", "Other Appliances"],
    "Kitchen & Dining": ["Cookware (Cooker, Kadai, Tawa)", "Gas Stoves", "Mixer Grinders",
                          "Dinner Sets & Crockery", "Storage Containers", "Cutlery", "Water Bottles",
                          "Tiffin Boxes", "Other Kitchen Items"],
    "Furniture": ["Beds", "Sofas", "Tables & Chairs", "Wardrobes", "Bookshelves",
                  "Mattresses", "Office Furniture", "Other Furniture"],
    "Fashion - Men": ["Shirts", "T-Shirts", "Jeans & Trousers", "Kurta & Ethnic Wear",
                       "Jackets & Sweaters", "Innerwear", "Other Men's Fashion"],
    "Fashion - Women": ["Saree", "Kurti & Suits", "Dresses & Gowns", "Tops & Tees",
                         "Jeans & Leggings", "Lehenga", "Innerwear", "Other Women's Fashion"],
    "Fashion - Kids": ["Boys Clothing", "Girls Clothing", "Baby Clothing", "School Uniforms",
                        "Other Kids Fashion"],
    "Footwear": ["Men's Shoes", "Women's Shoes", "Kids Footwear", "Sandals & Slippers",
                 "Sports Shoes", "Formal Shoes", "Other Footwear"],
    "Bags & Luggage": ["Handbags", "Backpacks", "Wallets", "Suitcases & Trolleys", "School Bags",
                        "Other Bags"],
    "Jewelry & Watches": ["Gold & Silver Jewelry", "Artificial Jewelry", "Men's Watches",
                           "Women's Watches", "Other"],
    "Beauty & Personal Care": ["Skincare", "Haircare", "Makeup", "Perfumes & Deodorants",
                                "Grooming (Razors, Trimmers)", "Bath & Body", "Other Beauty"],
    "Health & Medicine": ["Medicines (OTC)", "First Aid", "Ayurvedic & Herbal",
                           "Health Devices (BP, Sugar)", "Vitamins & Supplements", "Other Health"],
    "Grocery & Food": ["Atta, Rice & Dal", "Oil & Ghee", "Spices & Masala", "Tea & Coffee",
                        "Snacks & Namkeen", "Biscuits & Chocolates", "Dairy Products",
                        "Fruits & Vegetables", "Bakery Items", "Beverages", "Other Grocery"],
    "Baby & Kids Products": ["Diapers & Wipes", "Baby Food", "Feeding Bottles", "Baby Toys",
                              "Strollers & Cribs", "Other Baby Items"],
    "Toys & Games": ["Action Figures", "Board Games", "Remote Control Toys", "Educational Toys",
                      "Outdoor Play", "Other Toys"],
    "Sports & Fitness": ["Cricket", "Football", "Gym Equipment", "Cycles", "Yoga Mats",
                          "Sportswear", "Other Sports Items"],
    "Automotive": ["Bikes", "Bike Accessories & Spare Parts", "Car Accessories", "Helmets",
                    "Motor Oil & Lubricants", "Tyres", "Other Automotive"],
    "Books & Stationery": ["School Books", "Notebooks & Diaries", "Pens & Pencils",
                            "Art Supplies", "Novels & Story Books", "Office Stationery", "Other"],
    "Tools & Hardware": ["Hand Tools (Hammer, Screwdriver, etc.)", "Power Tools", "Electrical Items",
                          "Plumbing Items", "Paints", "Locks & Security", "Other Hardware"],
    "Garden & Outdoor": ["Plants & Seeds", "Gardening Tools", "Pots", "Outdoor Furniture",
                          "Other Garden Items"],
    "Pet Supplies": ["Pet Food", "Pet Toys", "Pet Grooming", "Pet Accessories", "Other Pet Items"],
    "Musical Instruments": ["Guitars", "Keyboards & Pianos", "Tabla & Percussion",
                             "Other Instruments"],
    "Mobile & Computer Repair Parts": ["Mobile Spare Parts", "Laptop Spare Parts",
                                        "Screen Guards & Covers", "Other Parts"],
    "Gifts & Occasions": ["Greeting Cards", "Gift Items", "Festive Decor", "Other Gifts"],
    "Industrial & Scientific": ["Lab Equipment", "Safety Gear", "Packaging Material", "Other"],
    "Other": ["Anything Else Not Listed"],
}

CATEGORY_SUGGESTIONS = list(CATEGORY_TREE.keys())


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_column_if_missing(conn, table, column, coltype):
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS buyers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT
        )
    """)

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
            is_approved INTEGER DEFAULT 1,
            is_banned INTEGER DEFAULT 0,
            free_delivery_threshold REAL DEFAULT 0,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shopkeeper_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            brand TEXT,
            specifications TEXT,
            unit TEXT DEFAULT 'piece',
            price REAL NOT NULL,
            stock_qty INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            category TEXT DEFAULT 'Other',
            subcategory TEXT,
            image_path TEXT,
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
            is_banned INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    # orders = cart header (one shop, one delivery, possibly many items)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            buyer_name TEXT,
            buyer_phone TEXT,
            buyer_lat REAL,
            buyer_lng REAL,
            buyer_address TEXT,
            shopkeeper_id INTEGER,
            subtotal REAL,
            distance_km REAL,
            delivery_charge REAL,
            total_amount REAL,
            commission_amount REAL,
            delivery_boy_id INTEGER,
            status TEXT DEFAULT 'Placed',
            created_at TEXT,
            FOREIGN KEY (shopkeeper_id) REFERENCES shopkeepers(id),
            FOREIGN KEY (delivery_boy_id) REFERENCES delivery_boys(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            item_id INTEGER,
            item_name TEXT,
            price REAL,
            quantity INTEGER,
            FOREIGN KEY (order_id) REFERENCES orders(id)
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            shopkeeper_id INTEGER,
            delivery_boy_id INTEGER,
            shop_rating INTEGER,
            shop_review TEXT,
            delivery_rating INTEGER,
            delivery_review TEXT,
            created_at TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
    """)

    conn.commit()

    # Safe migrations for anyone upgrading from the older single-item schema
    _add_column_if_missing(conn, "items", "category", "TEXT DEFAULT 'Other'")
    _add_column_if_missing(conn, "items", "subcategory", "TEXT")
    _add_column_if_missing(conn, "items", "image_path", "TEXT")
    _add_column_if_missing(conn, "items", "brand", "TEXT")
    _add_column_if_missing(conn, "items", "specifications", "TEXT")
    _add_column_if_missing(conn, "items", "unit", "TEXT DEFAULT 'piece'")
    _add_column_if_missing(conn, "shopkeepers", "is_approved", "INTEGER DEFAULT 1")
    _add_column_if_missing(conn, "shopkeepers", "is_banned", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "shopkeepers", "free_delivery_threshold", "REAL DEFAULT 0")
    _add_column_if_missing(conn, "delivery_boys", "is_banned", "INTEGER DEFAULT 0")
    conn.commit()
    conn.close()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------- Buyer functions ----------------

def create_buyer(name, phone, password):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO buyers (name, phone, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (name, phone, hash_password(password), now_str())
        )
        conn.commit()
        return True, "Account created."
    except sqlite3.IntegrityError:
        return False, "Ye phone number pehle se registered hai."
    finally:
        conn.close()


def authenticate_buyer(phone, password):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM buyers WHERE phone=? AND password_hash=?",
        (phone, hash_password(password))
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_buyer(buyer_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM buyers WHERE id=?", (buyer_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------- Shopkeeper functions ----------------

def create_shopkeeper(shop_name, owner_name, phone, password, upi_id):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO shopkeepers
               (shop_name, owner_name, phone, password_hash, upi_id, wallet_balance,
                is_approved, is_banned, free_delivery_threshold, created_at)
               VALUES (?, ?, ?, ?, ?, 0, 1, 0, 0, ?)""",
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


def update_free_delivery_threshold(shopkeeper_id, threshold):
    """threshold = 0 means free delivery is OFF. Any positive amount = order value
    above which delivery becomes free."""
    conn = get_connection()
    conn.execute("UPDATE shopkeepers SET free_delivery_threshold=? WHERE id=?", (threshold, shopkeeper_id))
    conn.commit()
    conn.close()


def recharge_wallet(shopkeeper_id, amount):
    """Shopkeeper recharges wallet. Platform takes RECHARGE_COMMISSION_PERCENT cut.
    Enforces MIN_RECHARGE_AMOUNT — call validate_recharge_amount() before this
    in the UI so the user gets a friendly error instead of an exception."""
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


def approve_shopkeeper(shopkeeper_id, approved=True):
    conn = get_connection()
    conn.execute("UPDATE shopkeepers SET is_approved=? WHERE id=?", (int(approved), shopkeeper_id))
    conn.commit()
    conn.close()


def set_shopkeeper_ban(shopkeeper_id, banned=True):
    conn = get_connection()
    conn.execute("UPDATE shopkeepers SET is_banned=? WHERE id=?", (int(banned), shopkeeper_id))
    conn.commit()
    conn.close()


def set_delivery_boy_ban(delivery_boy_id, banned=True):
    conn = get_connection()
    conn.execute("UPDATE delivery_boys SET is_banned=? WHERE id=?", (int(banned), delivery_boy_id))
    conn.commit()
    conn.close()


# ---------------- Item functions ----------------

def add_item(shopkeeper_id, item_name, price, stock_qty, category="Other", subcategory=None,
             image_path=None, brand=None, specifications=None, unit="piece"):
    conn = get_connection()
    conn.execute(
        """INSERT INTO items (shopkeeper_id, item_name, price, stock_qty, is_active, category,
                               subcategory, image_path, brand, specifications, unit)
           VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
        (shopkeeper_id, item_name, price, stock_qty, category, subcategory, image_path,
         brand, specifications, unit)
    )
    conn.commit()
    conn.close()


def bulk_add_items(shopkeeper_id, rows):
    """rows: list of dicts with keys item_name, price, stock_qty, category (optional), subcategory (optional)"""
    conn = get_connection()
    for r in rows:
        conn.execute(
            """INSERT INTO items (shopkeeper_id, item_name, price, stock_qty, is_active, category, subcategory)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (shopkeeper_id, r["item_name"], float(r["price"]), int(r["stock_qty"]),
             r.get("category", "Other") or "Other", r.get("subcategory") or None)
        )
    conn.commit()
    conn.close()


def get_main_categories():
    return list(CATEGORY_TREE.keys())


def get_subcategories(main_category):
    return CATEGORY_TREE.get(main_category, ["Other"])


def get_distinct_categories():
    """Live list of categories that shopkeepers have actually typed in,
    used to populate the buyer's filter dropdown (no fixed category list)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT category FROM items WHERE category IS NOT NULL AND category != '' "
        "ORDER BY category"
    ).fetchall()
    conn.close()
    return [r["category"] for r in rows]


def get_items_for_shop(shopkeeper_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM items WHERE shopkeeper_id=? ORDER BY id DESC", (shopkeeper_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_low_stock_items(shopkeeper_id, threshold=LOW_STOCK_THRESHOLD):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM items WHERE shopkeeper_id=? AND stock_qty <= ? AND is_active=1",
        (shopkeeper_id, threshold)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_item(item_id, item_name, price, stock_qty, is_active, category=None, subcategory=None,
                 image_path=None, brand=None, specifications=None, unit=None):
    conn = get_connection()
    if category is not None:
        conn.execute(
            "UPDATE items SET item_name=?, price=?, stock_qty=?, is_active=?, category=? WHERE id=?",
            (item_name, price, stock_qty, is_active, category, item_id)
        )
    else:
        conn.execute(
            "UPDATE items SET item_name=?, price=?, stock_qty=?, is_active=? WHERE id=?",
            (item_name, price, stock_qty, is_active, item_id)
        )
    if subcategory is not None:
        conn.execute("UPDATE items SET subcategory=? WHERE id=?", (subcategory, item_id))
    if image_path is not None:
        conn.execute("UPDATE items SET image_path=? WHERE id=?", (image_path, item_id))
    if brand is not None:
        conn.execute("UPDATE items SET brand=? WHERE id=?", (brand, item_id))
    if specifications is not None:
        conn.execute("UPDATE items SET specifications=? WHERE id=?", (specifications, item_id))
    if unit is not None:
        conn.execute("UPDATE items SET unit=? WHERE id=?", (unit, item_id))
    conn.commit()
    conn.close()


def delete_item(item_id):
    conn = get_connection()
    conn.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()


def search_items_with_shop(query, category=None, subcategory=None, min_price=None, max_price=None, brand=None):
    conn = get_connection()
    sql = """
        SELECT items.id as item_id, items.item_name, items.price, items.stock_qty,
               items.category, items.subcategory, items.image_path, items.brand,
               items.specifications, items.unit,
               shopkeepers.id as shopkeeper_id, shopkeepers.shop_name, shopkeepers.upi_id,
               shopkeepers.latitude, shopkeepers.longitude, shopkeepers.address,
               shopkeepers.wallet_balance, shopkeepers.free_delivery_threshold
        FROM items
        JOIN shopkeepers ON items.shopkeeper_id = shopkeepers.id
        WHERE items.is_active = 1
          AND items.stock_qty > 0
          AND shopkeepers.wallet_balance > 0
          AND shopkeepers.is_approved = 1
          AND shopkeepers.is_banned = 0
          AND shopkeepers.latitude IS NOT NULL
          AND items.item_name LIKE ?
    """
    params = [f"%{query}%"]
    if category and category != "All":
        sql += " AND items.category = ?"
        params.append(category)
    if subcategory and subcategory != "All":
        sql += " AND items.subcategory = ?"
        params.append(subcategory)
    if min_price is not None:
        sql += " AND items.price >= ?"
        params.append(min_price)
    if max_price is not None:
        sql += " AND items.price <= ?"
        params.append(max_price)
    if brand:
        sql += " AND items.brand LIKE ?"
        params.append(f"%{brand}%")
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def browse_items_by_category(category, subcategory=None):
    conn = get_connection()
    sql = """
        SELECT items.id as item_id, items.item_name, items.price, items.stock_qty,
               items.category, items.subcategory, items.image_path, items.brand,
               items.specifications, items.unit,
               shopkeepers.id as shopkeeper_id, shopkeepers.shop_name, shopkeepers.upi_id,
               shopkeepers.latitude, shopkeepers.longitude, shopkeepers.address,
               shopkeepers.wallet_balance, shopkeepers.free_delivery_threshold
        FROM items
        JOIN shopkeepers ON items.shopkeeper_id = shopkeepers.id
        WHERE items.is_active = 1 AND items.stock_qty > 0
          AND shopkeepers.wallet_balance > 0 AND shopkeepers.is_approved = 1
          AND shopkeepers.is_banned = 0 AND shopkeepers.latitude IS NOT NULL
          AND items.category = ?
    """
    params = [category]
    if subcategory and subcategory != "All":
        sql += " AND items.subcategory = ?"
        params.append(subcategory)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------- Delivery boy functions ----------------

def create_delivery_boy(name, phone, password):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO delivery_boys (name, phone, password_hash, is_available, is_banned, created_at) "
            "VALUES (?, ?, ?, 1, 0, ?)",
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
    rows = conn.execute("SELECT * FROM delivery_boys WHERE is_available=1 AND is_banned=0").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_orders_for_delivery_boy(delivery_boy_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM orders WHERE delivery_boy_id=? ORDER BY id DESC", (delivery_boy_id,)
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


def get_delivery_boy_earnings(delivery_boy_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(delivery_charge),0) s, COUNT(*) c FROM orders "
        "WHERE delivery_boy_id=? AND status='Delivered'",
        (delivery_boy_id,)
    ).fetchone()
    today = datetime.now().strftime("%Y-%m-%d")
    today_row = conn.execute(
        "SELECT COALESCE(SUM(delivery_charge),0) s, COUNT(*) c FROM orders "
        "WHERE delivery_boy_id=? AND status='Delivered' AND created_at LIKE ?",
        (delivery_boy_id, f"{today}%")
    ).fetchone()
    conn.close()
    return {
        "total_earning": round(row["s"], 2), "total_deliveries": row["c"],
        "today_earning": round(today_row["s"], 2), "today_deliveries": today_row["c"],
    }


def get_delivery_boy_rating_avg(delivery_boy_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT AVG(delivery_rating) a, COUNT(delivery_rating) c FROM ratings WHERE delivery_boy_id=? "
        "AND delivery_rating IS NOT NULL",
        (delivery_boy_id,)
    ).fetchone()
    conn.close()
    return (round(row["a"], 1) if row["a"] else None, row["c"])


# ---------------- Order (cart) functions ----------------

def create_order_with_items(buyer_name, buyer_phone, buyer_lat, buyer_lng, buyer_address,
                             shopkeeper_id, cart_items, distance_km, delivery_charge):
    """cart_items: list of dicts {item_id, item_name, price, quantity}"""
    subtotal = round(sum(i["price"] * i["quantity"] for i in cart_items), 2)
    total_amount = round(subtotal + delivery_charge, 2)
    commission, new_balance = deduct_order_commission(shopkeeper_id, total_amount)

    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO orders
        (buyer_name, buyer_phone, buyer_lat, buyer_lng, buyer_address, shopkeeper_id,
         subtotal, distance_km, delivery_charge, total_amount, commission_amount, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Placed', ?)
    """, (buyer_name, buyer_phone, buyer_lat, buyer_lng, buyer_address, shopkeeper_id,
          subtotal, distance_km, delivery_charge, total_amount, commission, now_str()))
    order_id = cur.lastrowid

    for item in cart_items:
        conn.execute(
            "INSERT INTO order_items (order_id, item_id, item_name, price, quantity) VALUES (?, ?, ?, ?, ?)",
            (order_id, item["item_id"], item["item_name"], item["price"], item["quantity"])
        )
        # reduce stock
        conn.execute("UPDATE items SET stock_qty = stock_qty - ? WHERE id = ?", (item["quantity"], item["item_id"]))

    conn.commit()
    conn.close()
    return order_id, total_amount, commission


def get_order_items(order_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_orders_for_shop(shopkeeper_id):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM orders WHERE shopkeeper_id=? ORDER BY id DESC", (shopkeeper_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_orders_for_buyer(buyer_phone):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM orders WHERE buyer_phone=? ORDER BY id DESC", (buyer_phone,)
    ).fetchall()
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


def get_order(order_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------- Ratings ----------------

def add_rating(order_id, shopkeeper_id, delivery_boy_id, shop_rating, shop_review,
                delivery_rating, delivery_review):
    conn = get_connection()
    conn.execute("""
        INSERT INTO ratings (order_id, shopkeeper_id, delivery_boy_id, shop_rating, shop_review,
                              delivery_rating, delivery_review, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (order_id, shopkeeper_id, delivery_boy_id, shop_rating, shop_review,
          delivery_rating, delivery_review, now_str()))
    conn.commit()
    conn.close()


def has_rating(order_id):
    conn = get_connection()
    row = conn.execute("SELECT id FROM ratings WHERE order_id=?", (order_id,)).fetchone()
    conn.close()
    return row is not None


def get_shop_rating_avg(shopkeeper_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT AVG(shop_rating) a, COUNT(shop_rating) c FROM ratings WHERE shopkeeper_id=? "
        "AND shop_rating IS NOT NULL",
        (shopkeeper_id,)
    ).fetchone()
    conn.close()
    return (round(row["a"], 1) if row["a"] else None, row["c"])


def get_shop_reviews(shopkeeper_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM ratings WHERE shopkeeper_id=? AND shop_review IS NOT NULL AND shop_review != '' "
        "ORDER BY id DESC LIMIT 20",
        (shopkeeper_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


def get_daily_order_stats(days=14):
    conn = get_connection()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT substr(created_at, 1, 10) as day, COUNT(*) as order_count,
               COALESCE(SUM(total_amount),0) as revenue
        FROM orders
        WHERE substr(created_at, 1, 10) >= ?
        GROUP BY day ORDER BY day
    """, (since,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_shopkeepers_admin():
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, shop_name, owner_name, phone, wallet_balance, is_approved, is_banned,
               latitude, longitude
        FROM shopkeepers ORDER BY id DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_delivery_boys_admin():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, phone, is_available, is_banned FROM delivery_boys ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
