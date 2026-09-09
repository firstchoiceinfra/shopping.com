"""
app.py - Single-page LocalMarket app.

Ek hi page mein: Home / Buyer / Shopkeeper / Delivery Boy / Admin.
Sidebar radio se view switch hoti hai - koi alag page load nahi hoti,
isliye multi-page navigation ka flicker nahi aata.
"""

import os
import streamlit as st
import pandas as pd
import db
from utils import haversine_km, calculate_delivery_charge, estimate_delivery_time, generate_upi_qr, image_to_bytes

st.set_page_config(page_title="LocalMarket", page_icon="🛒", layout="centered")
db.init_db()

# ---------------------------------------------------------------------------
# Colorful, modern e-commerce-style theming (original design — buttons,
# banners, badges in a vibrant multi-color palette).
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .stApp { background-color: #f5f7fb; }

    .lm-banner {
        background: linear-gradient(90deg, #2874f0 0%, #1dbf73 100%);
        padding: 18px 22px; border-radius: 14px; margin-bottom: 18px;
        color: white; box-shadow: 0 4px 14px rgba(40,116,240,0.25);
    }
    .lm-banner h1 { color: white !important; margin: 0; font-size: 26px; }
    .lm-banner p { color: #eaf3ff; margin: 2px 0 0 0; font-size: 14px; }

    .lm-badge {
        display: inline-block; padding: 3px 10px; border-radius: 20px;
        font-size: 12px; font-weight: 600; margin-right: 6px;
    }
    .lm-badge-orange { background: #fff3e0; color: #e65100; }
    .lm-badge-green { background: #e6f7ee; color: #1dbf73; }
    .lm-badge-blue { background: #e8f0fe; color: #2874f0; }
    .lm-badge-purple { background: #f3e8fe; color: #8e24aa; }

    div.stButton > button {
        border-radius: 8px; font-weight: 600; border: none;
        background: linear-gradient(90deg, #ff9f00 0%, #ff6f00 100%);
        color: white; transition: 0.2s;
    }
    div.stButton > button:hover { opacity: 0.9; transform: translateY(-1px); }

    div[data-testid="stForm"] div.stButton > button {
        background: linear-gradient(90deg, #2874f0 0%, #1a56c4 100%);
    }

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }
    section[data-testid="stSidebar"] * { color: #f0f0f0 !important; }

    div[data-testid="stMetricValue"] { color: #2874f0; }
</style>
""", unsafe_allow_html=True)

IMAGES_DIR = "uploaded_images"
os.makedirs(IMAGES_DIR, exist_ok=True)

if "view" not in st.session_state:
    st.session_state["view"] = "Home"
if "cart" not in st.session_state:
    st.session_state["cart"] = {}  # {shopkeeper_id: [ {item_id, item_name, price, unit, quantity}, ... ]}

with st.sidebar:
    st.markdown("## 🛒 LocalMarket")
    view = st.radio(
        "Role choose karo",
        ["Home", "🛍️ Buyer", "🏪 Shopkeeper", "🛵 Delivery Boy", "🛠️ Admin"],
        index=["Home", "🛍️ Buyer", "🏪 Shopkeeper", "🛵 Delivery Boy", "🛠️ Admin"].index(st.session_state["view"])
    )
    st.session_state["view"] = view


def render_home():
    st.markdown("""
    <div class="lm-banner">
        <h1>🛒 LocalMarket</h1>
        <p>Kahin se bhi order karo, kisi bhi ghar ke liye — 1-3 ghante mein delivery.</p>
    </div>
    """, unsafe_allow_html=True)

    b1, b2, b3 = st.columns(3)
    b1.markdown('<span class="lm-badge lm-badge-blue">🛍️ Buyer</span>', unsafe_allow_html=True)
    b2.markdown('<span class="lm-badge lm-badge-orange">🏪 Shopkeeper</span>', unsafe_allow_html=True)
    b3.markdown('<span class="lm-badge lm-badge-green">🛵 Delivery</span>', unsafe_allow_html=True)

    st.markdown("""
Ye ek **hyperlocal marketplace** hai jisme:
- 🛍️ **Buyer** kisi bhi delivery address (apne shehar ya kisi doosre shehar) ke liye,
  us address ke sabse nazdeek shopkeepers se koi bhi cheez order kar sakta hai
- 🏪 **Shopkeeper** apna stock (brand, specification, photo, unit-wise price) list karta hai
- 🛵 **Delivery Boy** orders accept karke deliver karta hai (ya shopkeeper khud bhej sakta hai)

Payment seedha shopkeeper ke UPI par jata hai. Platform commission:
- Wallet recharge par **2%** (minimum recharge ₹100)
- Har order par **2%** wallet se auto-deduct

👈 **Left sidebar** se apna role choose karo.
""")


def location_picker(key_prefix, label="📍 Delivery location"):
    """
    Reusable location picker. Buyer can EITHER auto-detect their current
    location OR manually type coordinates for a totally different address
    (e.g. sitting in Mumbai, ordering for a Nagpur home).
    Returns (lat, lng).
    """
    st.subheader(label)
    st.caption("Apni current location use karo, YA kisi doosre shehar/ghar ke liye manually address set karo.")

    mode = st.radio(
        "Location kaise set karein?",
        ["📡 Meri current location", "✍️ Alag address manually daalo"],
        key=f"{key_prefix}_mode", horizontal=True
    )

    lat_key, lng_key = f"{key_prefix}_lat", f"{key_prefix}_lng"

    if mode == "📡 Meri current location":
        try:
            from streamlit_js_eval import get_geolocation
            if st.button("📡 Auto-detect karo", key=f"{key_prefix}_gps"):
                loc = get_geolocation()
                if loc and "coords" in loc:
                    st.session_state[lat_key] = loc["coords"]["latitude"]
                    st.session_state[lng_key] = loc["coords"]["longitude"]
                    st.success("Location detect ho gayi!")
        except Exception:
            st.caption("(Auto-detect deploy hone ke baad browser permission maangega.)")

    c1, c2 = st.columns(2)
    lat = c1.number_input("Latitude", value=st.session_state.get(lat_key, 28.6139), format="%.6f", key=f"{key_prefix}_lat_in")
    lng = c2.number_input("Longitude", value=st.session_state.get(lng_key, 77.2090), format="%.6f", key=f"{key_prefix}_lng_in")
    st.session_state[lat_key] = lat
    st.session_state[lng_key] = lng

    if mode == "✍️ Alag address manually daalo":
        st.caption("💡 Tip: Google Maps par address search karo, right-click → coordinates copy karo, yahan paste karo.")

    return lat, lng


def render_buyer():
    st.markdown("""
    <div class="lm-banner">
        <h1>🛍️ Buyer</h1>
        <p>Kuch bhi order karo, kahin bhi deliver karwao.</p>
    </div>
    """, unsafe_allow_html=True)

    # ---- Login gate: login/signup zaroori hai, bina login ke search nahi ----
    if "buyer_id" not in st.session_state:
        st.info("🔐 Search aur order karne ke liye pehle login ya account banao.")
        tab_login, tab_signup = st.tabs(["Login", "Naya Account Banao"])

        with tab_login:
            phone = st.text_input("Phone number", key="b_login_phone")
            password = st.text_input("Password", type="password", key="b_login_pw")
            if st.button("Login", key="b_login_btn"):
                buyer = db.authenticate_buyer(phone, password)
                if buyer:
                    st.session_state["buyer_id"] = buyer["id"]
                    st.rerun()
                else:
                    st.error("Galat phone number ya password.")

        with tab_signup:
            name = st.text_input("Aapka naam", key="b_signup_name")
            phone2 = st.text_input("Phone number", key="b_signup_phone")
            password2 = st.text_input("Password banao", type="password", key="b_signup_pw")
            if st.button("Account Banao", key="b_signup_btn"):
                if not all([name, phone2, password2]):
                    st.error("Sab fields bharna zaroori hai.")
                else:
                    ok, msg = db.create_buyer(name, phone2, password2)
                    if ok:
                        st.success(msg + " Ab Login tab se login karo.")
                    else:
                        st.error(msg)
        return

    buyer = db.get_buyer(st.session_state["buyer_id"])
    col1, col2 = st.columns([3, 1])
    with col1:
        st.write(f"👋 Namaste, **{buyer['name']}**")
    with col2:
        if st.button("Logout", key="b_logout"):
            del st.session_state["buyer_id"]
            st.rerun()

    lat, lng = location_picker("buyer")
    buyer_address = st.text_input("Poora delivery address (house no, street, landmark, city)", key="buyer_address")

    st.divider()
    st.subheader("🔍 Item dhoondo")

    fc1, fc2 = st.columns(2)
    query = fc1.text_input("Kya chahiye? (e.g. 'chai patti', 'phone charger')", key="buyer_query")
    main_cat_filter = fc2.selectbox("Main Category", ["All"] + db.get_main_categories(), key="buyer_cat_filter")

    sub_cat_filter = "All"
    if main_cat_filter != "All":
        sub_cat_filter = st.selectbox(
            "Sub-category", ["All"] + db.get_subcategories(main_cat_filter), key="buyer_subcat_filter"
        )

    with st.expander("🔧 Aur filters (brand, price range)"):
        fc3, fc4, fc5 = st.columns(3)
        brand_filter = fc3.text_input("Brand (optional)", key="buyer_brand_filter")
        min_price = fc4.number_input("Min price ₹", min_value=0.0, value=0.0, step=10.0, key="buyer_min_price")
        max_price = fc5.number_input("Max price ₹ (0 = no limit)", min_value=0.0, value=0.0, step=10.0, key="buyer_max_price")

    if query:
        results = db.search_items_with_shop(
            query,
            category=main_cat_filter if main_cat_filter != "All" else None,
            subcategory=sub_cat_filter if sub_cat_filter != "All" else None,
            min_price=min_price if min_price > 0 else None,
            max_price=max_price if max_price > 0 else None,
            brand=brand_filter if brand_filter else None,
        )

        if not results:
            st.warning("Koi shopkeeper nahi mila jo ye item bech raha ho abhi. Filters hata ke dekho.")
        else:
            for r in results:
                r["distance_km"] = haversine_km(lat, lng, r["latitude"], r["longitude"])
            results = [r for r in results if r["distance_km"] is not None]
            results.sort(key=lambda r: r["distance_km"])

            st.write(f"**{len(results)} option(s)** mile — nazdeek se door:")

            for r in results:
                with st.container(border=True):
                    img_col, info_col = st.columns([1, 3])
                    with img_col:
                        if r.get("image_path") and os.path.exists(r["image_path"]):
                            st.image(r["image_path"], width=80)
                        else:
                            st.write("📦")
                    with info_col:
                        brand_txt = f" | Brand: {r['brand']}" if r.get("brand") else ""
                        st.markdown(f"**{r['item_name']}**{brand_txt}")
                        st.caption(f"🏪 {r['shop_name']} | 📍 {r['distance_km']:.2f} km door | "
                                   f"⏱️ {estimate_delivery_time(r['distance_km'])}")
                        if r.get("specifications"):
                            st.caption(f"Spec: {r['specifications']}")
                        st.write(f"₹{r['price']} per {r['unit']} | Stock: {r['stock_qty']} {r['unit']}")

                    qty_col1, qty_col2 = st.columns([2, 1])
                    qty = qty_col1.number_input(
                        f"Quantity ({r['unit']})", min_value=1, value=1, step=1,
                        key=f"qty_{r['item_id']}_{r['shopkeeper_id']}"
                    )
                    if not r["upi_id"]:
                        qty_col2.caption("⚠️ UPI nahi hai, order nahi ho sakta")
                    else:
                        if qty_col2.button("🛒 Cart mein daalo", key=f"addcart_{r['item_id']}_{r['shopkeeper_id']}"):
                            shop_id = r["shopkeeper_id"]
                            cart = st.session_state["cart"]
                            if shop_id not in cart:
                                cart[shop_id] = {"shop_info": r, "items": {}}
                            cart[shop_id]["items"][r["item_id"]] = {
                                "item_id": r["item_id"], "item_name": r["item_name"],
                                "price": r["price"], "unit": r["unit"], "quantity": qty,
                            }
                            st.success(f"{r['item_name']} cart mein add ho gaya!")

    # ---------------- CART ----------------
    if st.session_state["cart"]:
        st.divider()
        st.subheader("🛒 Aapka Cart")
        st.caption("Note: ek order ek hi shop se ban sakta hai (ek hi UPI payment jata hai). "
                   "Alag shop ke items ke liye alag order karo.")

        for shop_id, cart_data in list(st.session_state["cart"].items()):
            shop_info = cart_data["shop_info"]
            items = cart_data["items"]
            if not items:
                continue

            with st.container(border=True):
                st.markdown(f"**🏪 {shop_info['shop_name']}**")
                subtotal = 0
                for iid, it in list(items.items()):
                    line_total = round(it["price"] * it["quantity"], 2)
                    subtotal += line_total
                    cc1, cc2, cc3 = st.columns([3, 1, 1])
                    cc1.write(f"{it['item_name']} — {it['quantity']} {it['unit']} × ₹{it['price']}")
                    cc2.write(f"₹{line_total}")
                    if cc3.button("❌", key=f"remove_{shop_id}_{iid}"):
                        del items[iid]
                        st.rerun()

                distance_km = haversine_km(lat, lng, shop_info["latitude"], shop_info["longitude"])
                free_threshold = shop_info.get("free_delivery_threshold", 0)
                charge, km_slab, free_applied = calculate_delivery_charge(distance_km, subtotal, free_threshold)
                total = round(subtotal + charge, 2)

                st.write(f"Subtotal: ₹{subtotal}")
                if free_applied:
                    st.success(f"🎉 Free delivery! (₹{free_threshold}+ order)")
                else:
                    st.write(f"Delivery charge ({distance_km:.2f} km): ₹{charge}")
                    if free_threshold and free_threshold > 0:
                        st.caption(f"💡 ₹{free_threshold}+ ka order karo to delivery FREE ho jayegi "
                                   f"(abhi ₹{round(free_threshold - subtotal, 2)} aur chahiye)")
                st.write(f"**Total: ₹{total}**")
                st.caption(f"⏱️ Estimated delivery: {estimate_delivery_time(distance_km)}")

                if st.button(f"✅ Checkout — {shop_info['shop_name']}", key=f"checkout_{shop_id}"):
                    st.session_state["checkout_shop_id"] = shop_id

    # ---------------- CHECKOUT ----------------
    if st.session_state.get("checkout_shop_id") in st.session_state["cart"]:
        shop_id = st.session_state["checkout_shop_id"]
        cart_data = st.session_state["cart"][shop_id]
        shop_info = cart_data["shop_info"]
        items = list(cart_data["items"].values())

        st.divider()
        st.subheader("✅ Order confirm karo")
        with st.form("confirm_order_form"):
            buyer_name = st.text_input("Aapka naam", value=buyer["name"])
            buyer_phone = st.text_input("Aapka phone number", value=buyer["phone"])
            submitted = st.form_submit_button("Order place karo aur QR dikhao")

        if submitted:
            if not buyer_name or not buyer_phone or not buyer_address:
                st.error("Naam, phone aur delivery address bharna zaroori hai.")
            else:
                distance_km = haversine_km(lat, lng, shop_info["latitude"], shop_info["longitude"])
                subtotal = round(sum(i["price"] * i["quantity"] for i in items), 2)
                free_threshold = shop_info.get("free_delivery_threshold", 0)
                charge, km_slab, free_applied = calculate_delivery_charge(distance_km, subtotal, free_threshold)

                order_id, total_amount, commission = db.create_order_with_items(
                    buyer_name=buyer_name, buyer_phone=buyer_phone,
                    buyer_lat=lat, buyer_lng=lng, buyer_address=buyer_address,
                    shopkeeper_id=shop_id, cart_items=items,
                    distance_km=distance_km, delivery_charge=charge
                )

                st.success(f"🎉 Order #{order_id} place ho gaya!")
                st.write(f"**Total pay karna hai: ₹{total_amount}** seedha shopkeeper ko.")

                qr_img, upi_url = generate_upi_qr(shop_info["upi_id"], shop_info["shop_name"], total_amount,
                                                   note=f"Order #{order_id}")
                st.image(image_to_bytes(qr_img), caption="Is QR ko scan karke UPI se payment karo", width=250)
                st.caption(upi_url)

                del st.session_state["cart"][shop_id]
                del st.session_state["checkout_shop_id"]

    # ---------------- ORDER HISTORY ----------------
    st.divider()
    with st.expander("📜 Meri order history dekho"):
        history_phone = st.text_input("Apna phone number daalo", value=buyer["phone"], key="history_phone")
        if st.button("History dekho", key="history_btn"):
            orders = db.get_orders_for_buyer(history_phone)
            if not orders:
                st.caption("Koi order nahi mila is number se.")
            for o in orders:
                with st.container(border=True):
                    st.write(f"**Order #{o['id']}** — ₹{o['total_amount']} — Status: **{o['status']}**")
                    st.caption(f"Date: {o['created_at']}")
                    order_items = db.get_order_items(o["id"])
                    for oi in order_items:
                        st.caption(f"  • {oi['item_name']} × {oi['quantity']} — ₹{oi['price']}")

                    if o["status"] == "Delivered" and not db.has_rating(o["id"]):
                        st.markdown("**⭐ Is order ko rate karo**")
                        shop_r = st.slider("Shop rating", 1, 5, 5, key=f"shoprate_{o['id']}")
                        shop_rev = st.text_input("Shop review (optional)", key=f"shoprev_{o['id']}")
                        del_r = st.slider("Delivery rating", 1, 5, 5, key=f"delrate_{o['id']}") if o["delivery_boy_id"] else None
                        del_rev = st.text_input("Delivery review (optional)", key=f"delrev_{o['id']}") if o["delivery_boy_id"] else None
                        if st.button("Rating submit karo", key=f"submitrate_{o['id']}"):
                            db.add_rating(o["id"], o["shopkeeper_id"], o["delivery_boy_id"],
                                          shop_r, shop_rev, del_r, del_rev)
                            st.success("Rating submit ho gayi, dhanyavaad!")
                            st.rerun()


def render_shopkeeper():
    st.markdown("""
    <div class="lm-banner" style="background: linear-gradient(90deg, #ff9f00 0%, #e65100 100%);">
        <h1>🏪 Shopkeeper Panel</h1>
        <p>Apni dukaan online lao, orders lo, kamao.</p>
    </div>
    """, unsafe_allow_html=True)

    if "shop_id" not in st.session_state:
        tab_login, tab_signup = st.tabs(["Login", "Naya Account Banao"])

        with tab_login:
            phone = st.text_input("Phone number", key="s_login_phone")
            password = st.text_input("Password", type="password", key="s_login_pw")
            if st.button("Login", key="s_login_btn"):
                shop = db.authenticate_shopkeeper(phone, password)
                if shop:
                    if shop["is_banned"]:
                        st.error("Ye account ban kar diya gaya hai. Admin se contact karo.")
                    else:
                        st.session_state["shop_id"] = shop["id"]
                        st.rerun()
                else:
                    st.error("Galat phone number ya password.")

        with tab_signup:
            shop_name = st.text_input("Dukaan ka naam", key="s_signup_shop")
            owner_name = st.text_input("Aapka naam", key="s_signup_owner")
            phone2 = st.text_input("Phone number", key="s_signup_phone")
            upi_id = st.text_input("UPI ID (e.g. yourname@okaxis)", key="s_signup_upi")
            password2 = st.text_input("Password banao", type="password", key="s_signup_pw")
            if st.button("Account Banao", key="s_signup_btn"):
                if not all([shop_name, owner_name, phone2, upi_id, password2]):
                    st.error("Sab fields bharna zaroori hai.")
                else:
                    ok, msg = db.create_shopkeeper(shop_name, owner_name, phone2, password2, upi_id)
                    if ok:
                        st.success(msg + " Ab Login tab se login karo.")
                    else:
                        st.error(msg)
        return

    shop = db.get_shopkeeper(st.session_state["shop_id"])
    if shop["is_banned"]:
        st.error("Ye account ban kar diya gaya hai.")
        if st.button("Logout"):
            del st.session_state["shop_id"]
            st.rerun()
        return

    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"Namaste, {shop['owner_name']} 👋 ({shop['shop_name']})")
    with col2:
        if st.button("Logout", key="s_logout"):
            del st.session_state["shop_id"]
            st.rerun()

    if not shop["is_approved"]:
        st.warning("⏳ Aapka account abhi admin approval ka wait kar raha hai — approve hone ke baad hi listing live hogi.")

    balance = shop["wallet_balance"]
    if balance <= 0:
        st.error(f"⚠️ Wallet balance: ₹{balance:.2f} — Aapki listing PUBLISH NAHI hai. Recharge karo.")
    elif balance < db.LOW_BALANCE_THRESHOLD:
        st.warning(f"⚠️ Wallet balance kam hai: ₹{balance:.2f} — jaldi recharge kar lo warna listing band ho sakti hai.")
    else:
        st.success(f"💰 Wallet balance: ₹{balance:.2f} — Aapki listing LIVE hai.")

    avg_rating, rating_count = db.get_shop_rating_avg(shop["id"])
    if avg_rating:
        st.caption(f"⭐ Aapki rating: {avg_rating}/5 ({rating_count} reviews)")

    low_stock = db.get_low_stock_items(shop["id"])
    if low_stock:
        names = ", ".join(i["item_name"] for i in low_stock)
        st.warning(f"📉 Low stock alert: {names}")

    tabs = st.tabs(["💰 Wallet", "📦 Items", "📍 Shop Details", "🧾 Orders", "⭐ Reviews"])

    # ---------------- Wallet ----------------
    with tabs[0]:
        st.write(f"Recharge par **{db.RECHARGE_COMMISSION_PERCENT}%** commission, baaki wallet mein credit.")
        st.write(f"Har order par wallet se **{db.ORDER_COMMISSION_PERCENT}%** commission auto-deduct hota hai.")
        st.caption(f"Minimum recharge: ₹{db.MIN_RECHARGE_AMOUNT}")

        amount = st.number_input("Recharge amount (₹)", min_value=0.0, value=100.0, step=10.0, key="recharge_amt")
        if st.button("Recharge karo (demo payment)", key="recharge_btn"):
            if amount < db.MIN_RECHARGE_AMOUNT:
                st.error(f"Minimum recharge ₹{db.MIN_RECHARGE_AMOUNT} hai.")
            else:
                platform_cut, credited, new_balance = db.recharge_wallet(shop["id"], amount)
                st.success(f"₹{amount} recharge hua. Platform cut: ₹{platform_cut}, Credit: ₹{credited}. "
                           f"Naya balance: ₹{new_balance}")
                st.rerun()

        st.markdown("**Wallet History**")
        history = db.get_wallet_history(shop["id"])
        if history:
            st.dataframe(history, use_container_width=True, hide_index=True)
        else:
            st.caption("Abhi koi transaction nahi hui.")

    # ---------------- Items ----------------
    with tabs[1]:
        add_tab, bulk_tab = st.tabs(["Ek item add karo", "Bulk CSV upload"])

        with add_tab:
            st.markdown("**Category choose karo**")
            cat_col, subcat_col = st.columns(2)
            main_cat_choice = cat_col.selectbox("Main Category", db.get_main_categories(), key="add_item_main_cat")
            sub_options = db.get_subcategories(main_cat_choice)
            sub_cat_choice = subcat_col.selectbox("Sub-category", sub_options, key="add_item_sub_cat")

            custom_cat, custom_subcat = None, None
            if main_cat_choice == "Other":
                custom_cat = st.text_input("Apni category likho", key="add_item_custom_cat")
            if sub_cat_choice in ("Other Electronics", "Other", "Anything Else Not Listed",
                                   "Other Men's Fashion", "Other Women's Fashion", "Other Kids Fashion",
                                   "Other Footwear", "Other Bags", "Other Beauty", "Other Health",
                                   "Other Grocery", "Other Baby Items", "Other Toys", "Other Sports Items",
                                   "Other Automotive", "Other Appliances", "Other Kitchen Items",
                                   "Other Furniture", "Other Garden Items", "Other Pet Items",
                                   "Other Instruments", "Other Parts", "Other Gifts", "Other Hardware"):
                custom_subcat = st.text_input("Apni sub-category likho (optional, aur specific)", key="add_item_custom_subcat")

            with st.form("add_item_form", clear_on_submit=True):
                item_name = st.text_input("Item ka naam")
                brand = st.text_input("Brand (optional)")
                specifications = st.text_area("Specifications (optional) - jaise size, color, model", height=70)
                item_unit = st.selectbox("Unit", db.UNITS)
                price = st.number_input("Price per unit (Rs)", min_value=1.0, value=10.0, step=1.0)
                stock_qty = st.number_input("Stock quantity (in same unit)", min_value=0, value=10, step=1)
                photo = st.file_uploader("Item photo (optional)", type=["png", "jpg", "jpeg"])
                add_submitted = st.form_submit_button("Add karo")

            if add_submitted:
                if item_name:
                    image_path = None
                    if photo is not None:
                        image_path = os.path.join(IMAGES_DIR, f"{shop['id']}_{item_name.replace(' ', '_')}_{photo.name}")
                        with open(image_path, "wb") as f:
                            f.write(photo.getbuffer())
                    final_category = (custom_cat.strip() if custom_cat and custom_cat.strip() else main_cat_choice)
                    final_subcategory = (custom_subcat.strip() if custom_subcat and custom_subcat.strip() else sub_cat_choice)
                    db.add_item(shop["id"], item_name, price, stock_qty, category=final_category,
                                subcategory=final_subcategory, image_path=image_path, brand=brand,
                                specifications=specifications, unit=item_unit)
                    st.success(f"'{item_name}' add ho gaya!")
                    st.rerun()
                else:
                    st.error("Item ka naam daalo.")

        with bulk_tab:
            st.caption("CSV mein columns hone chahiye: item_name, price, stock_qty, category (optional)")
            csv_file = st.file_uploader("CSV upload karo", type=["csv"], key="bulk_csv")
            if csv_file is not None:
                try:
                    df = pd.read_csv(csv_file)
                    st.dataframe(df.head(10), use_container_width=True)
                    if st.button("In sab items ko add karo"):
                        rows = df.to_dict("records")
                        db.bulk_add_items(shop["id"], rows)
                        st.success(f"{len(rows)} items add ho gaye!")
                        st.rerun()
                except Exception as e:
                    st.error(f"CSV padhne mein error: {e}")

        st.markdown("**Aapke items**")
        items = db.get_items_for_shop(shop["id"])
        if not items:
            st.caption("Abhi koi item add nahi kiya.")
        for it in items:
            with st.container(border=True):
                if it.get("image_path") and os.path.exists(it["image_path"]):
                    st.image(it["image_path"], width=80)
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                c1.write(f"**{it['item_name']}** ({it.get('unit', 'piece')})")
                new_price = c2.number_input("Price", value=float(it["price"]), key=f"price_{it['id']}", min_value=1.0)
                new_stock = c3.number_input("Stock", value=int(it["stock_qty"]), key=f"stock_{it['id']}", min_value=0)
                is_active = c4.checkbox("Active", value=bool(it["is_active"]), key=f"active_{it['id']}")
                bcol1, bcol2 = st.columns(2)
                if bcol1.button("Update", key=f"update_{it['id']}"):
                    db.update_item(it["id"], it["item_name"], new_price, new_stock, int(is_active))
                    st.success("Updated!")
                    st.rerun()
                if bcol2.button("Delete", key=f"delete_{it['id']}"):
                    db.delete_item(it["id"])
                    st.rerun()

    # ---------------- Shop Details ----------------
    with tabs[2]:
        st.markdown("**Shop location** (buyer se distance calculate karne ke liye zaroori hai)")
        try:
            from streamlit_js_eval import get_geolocation
            if st.button("📡 Auto-detect current location", key="shop_gps"):
                loc = get_geolocation()
                if loc and "coords" in loc:
                    st.session_state["shop_lat"] = loc["coords"]["latitude"]
                    st.session_state["shop_lng"] = loc["coords"]["longitude"]
        except Exception:
            pass

        default_lat = st.session_state.get("shop_lat", shop["latitude"] or 28.6139)
        default_lng = st.session_state.get("shop_lng", shop["longitude"] or 77.2090)
        c1, c2 = st.columns(2)
        new_lat = c1.number_input("Latitude", value=float(default_lat), format="%.6f", key="shop_lat_input")
        new_lng = c2.number_input("Longitude", value=float(default_lng), format="%.6f", key="shop_lng_input")
        new_address = st.text_input("Address", value=shop["address"] or "", key="shop_address_input")

        if st.button("Location save karo", key="shop_loc_save"):
            db.update_shop_location(shop["id"], new_lat, new_lng, new_address)
            st.success("Location saved!")
            st.rerun()

        st.divider()
        st.markdown("**UPI ID**")
        new_upi = st.text_input("UPI ID", value=shop["upi_id"] or "", key="shop_upi_input")
        if st.button("UPI ID save karo", key="shop_upi_save"):
            db.update_shop_upi(shop["id"], new_upi)
            st.success("UPI ID updated!")
            st.rerun()

        st.divider()
        st.markdown("**Free Delivery Setting**")
        st.caption("Rs 0 rakho to free delivery OFF rahegi. Koi amount daalo (e.g. 500) to us amount+ ke "
                   "order par delivery FREE ho jayegi.")
        current_threshold = shop.get("free_delivery_threshold", 0) or 0
        new_threshold = st.number_input("Free delivery upar (Rs)", min_value=0.0, value=float(current_threshold), step=50.0)
        if st.button("Free delivery setting save karo"):
            db.update_free_delivery_threshold(shop["id"], new_threshold)
            st.success("Saved!")
            st.rerun()

    # ---------------- Orders ----------------
    with tabs[3]:
        orders = db.get_orders_for_shop(shop["id"])
        if not orders:
            st.caption("Abhi koi order nahi aaya.")
        delivery_boys = db.get_available_delivery_boys()
        db_options = {f"{d['name']} ({d['phone']})": d["id"] for d in delivery_boys}

        for o in orders:
            with st.container(border=True):
                st.write(f"**Order #{o['id']}** - Rs {o['total_amount']} - Status: **{o['status']}**")
                st.caption(f"Buyer: {o['buyer_name']} | {o['buyer_phone']} | {o['buyer_address']}")
                order_items = db.get_order_items(o["id"])
                for oi in order_items:
                    st.caption(f"  - {oi['item_name']} x {oi['quantity']} - Rs {oi['price']} each")
                st.caption(f"Distance: {o['distance_km']:.2f} km | Delivery: Rs {o['delivery_charge']} | "
                           f"Subtotal: Rs {o['subtotal']} | Commission: Rs {o['commission_amount']}")

                c1, c2 = st.columns(2)
                with c1:
                    status_options = ["Placed", "Preparing", "Out for Delivery", "Delivered", "Cancelled"]
                    new_status = st.selectbox("Status update karo", status_options,
                                               index=status_options.index(o["status"]), key=f"status_{o['id']}")
                    if st.button("Status save karo", key=f"save_status_{o['id']}"):
                        db.update_order_status(o["id"], new_status)
                        st.rerun()
                with c2:
                    st.caption("Khud deliver karo YA delivery boy assign karo:")
                    if db_options:
                        chosen = st.selectbox("Delivery boy assign karo", ["-- Khud deliver karunga --"] + list(db_options.keys()),
                                               key=f"db_{o['id']}")
                        if chosen != "-- Khud deliver karunga --" and st.button("Assign karo", key=f"assign_{o['id']}"):
                            db.assign_delivery_boy_to_order(o["id"], db_options[chosen])
                            st.rerun()
                    else:
                        st.caption("Koi delivery boy available nahi - khud deliver karo.")

    # ---------------- Reviews ----------------
    with tabs[4]:
        reviews = db.get_shop_reviews(shop["id"])
        if not reviews:
            st.caption("Abhi koi review nahi aaya.")
        for rv in reviews:
            with st.container(border=True):
                st.write(f"Rating: {rv['shop_rating']}/5")
                if rv["shop_review"]:
                    st.write(rv["shop_review"])
                st.caption(rv["created_at"])


def render_delivery_boy():
    st.markdown("""
    <div class="lm-banner" style="background: linear-gradient(90deg, #1dbf73 0%, #0d7a45 100%);">
        <h1>🛵 Delivery Boy Panel</h1>
        <p>Orders accept karo, deliver karo, kamao.</p>
    </div>
    """, unsafe_allow_html=True)

    if "delivery_id" not in st.session_state:
        tab_login, tab_signup = st.tabs(["Login", "Naya Account Banao"])
        with tab_login:
            phone = st.text_input("Phone number", key="d_login_phone")
            password = st.text_input("Password", type="password", key="d_login_pw")
            if st.button("Login", key="d_login_btn"):
                d = db.authenticate_delivery_boy(phone, password)
                if d:
                    if d["is_banned"]:
                        st.error("Ye account ban kar diya gaya hai.")
                    else:
                        st.session_state["delivery_id"] = d["id"]
                        st.rerun()
                else:
                    st.error("Galat phone number ya password.")
        with tab_signup:
            name = st.text_input("Aapka naam", key="d_signup_name")
            phone2 = st.text_input("Phone number", key="d_signup_phone")
            password2 = st.text_input("Password banao", type="password", key="d_signup_pw")
            if st.button("Account Banao", key="d_signup_btn"):
                if not all([name, phone2, password2]):
                    st.error("Sab fields bharna zaroori hai.")
                else:
                    ok, msg = db.create_delivery_boy(name, phone2, password2)
                    if ok:
                        st.success(msg + " Ab Login tab se login karo.")
                    else:
                        st.error(msg)
        return

    conn_row = db.get_connection()
    row = conn_row.execute("SELECT * FROM delivery_boys WHERE id=?", (st.session_state["delivery_id"],)).fetchone()
    conn_row.close()
    delivery_boy = dict(row)

    if delivery_boy["is_banned"]:
        st.error("Ye account ban kar diya gaya hai.")
        if st.button("Logout"):
            del st.session_state["delivery_id"]
            st.rerun()
        return

    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"Namaste, {delivery_boy['name']} 👋")
    with col2:
        if st.button("Logout", key="d_logout"):
            del st.session_state["delivery_id"]
            st.rerun()

    avg_rating, rcount = db.get_delivery_boy_rating_avg(delivery_boy["id"])
    if avg_rating:
        st.caption(f"⭐ Aapki rating: {avg_rating}/5 ({rcount} reviews)")

    earnings = db.get_delivery_boy_earnings(delivery_boy["id"])
    ec1, ec2, ec3, ec4 = st.columns(4)
    ec1.metric("Aaj ki kamai", f"₹{earnings['today_earning']}")
    ec2.metric("Aaj deliveries", earnings["today_deliveries"])
    ec3.metric("Total kamai", f"₹{earnings['total_earning']}")
    ec4.metric("Total deliveries", earnings["total_deliveries"])

    is_available = st.toggle("Available for delivery", value=bool(delivery_boy["is_available"]), key="d_avail")
    if is_available != bool(delivery_boy["is_available"]):
        db.set_delivery_boy_availability(delivery_boy["id"], is_available)
        st.rerun()

    st.markdown("**Apna current location update karo**")
    try:
        from streamlit_js_eval import get_geolocation
        if st.button("📡 Auto-detect location", key="d_gps"):
            loc = get_geolocation()
            if loc and "coords" in loc:
                st.session_state["dboy_lat"] = loc["coords"]["latitude"]
                st.session_state["dboy_lng"] = loc["coords"]["longitude"]
    except Exception:
        pass

    default_lat = st.session_state.get("dboy_lat", delivery_boy["latitude"] or 28.6139)
    default_lng = st.session_state.get("dboy_lng", delivery_boy["longitude"] or 77.2090)
    c1, c2 = st.columns(2)
    lat = c1.number_input("Latitude", value=float(default_lat), format="%.6f", key="d_lat_input")
    lng = c2.number_input("Longitude", value=float(default_lng), format="%.6f", key="d_lng_input")
    if st.button("Location save karo", key="d_loc_save"):
        db.update_delivery_boy_location(delivery_boy["id"], lat, lng)
        st.success("Location updated!")
        st.rerun()

    st.divider()
    st.subheader("📦 Available Orders (nazdeek se door)")
    open_orders = db.get_unassigned_orders_needing_delivery()
    for o in open_orders:
        dist = haversine_km(lat, lng, o["buyer_lat"], o["buyer_lng"])
        with st.container(border=True):
            order_items = db.get_order_items(o["id"])
            items_text = ", ".join(f"{oi['item_name']} x{oi['quantity']}" for oi in order_items)
            st.write(f"**Order #{o['id']}** — {items_text}")
            dist_text = f"{dist:.2f} km" if dist is not None else "N/A"
            st.caption(f"Deliver to: {o['buyer_address']} | Aapki duri: {dist_text}")
            st.caption(f"Delivery charge (aapki earning): ₹{o['delivery_charge']}")
            if st.button("Accept karo", key=f"accept_{o['id']}"):
                db.accept_order_as_delivery_boy(o["id"], delivery_boy["id"])
                st.rerun()
    if not open_orders:
        st.caption("Abhi koi naya order available nahi hai.")

    st.divider()
    st.subheader("🚚 Aapke Orders")
    my_orders = db.get_orders_for_delivery_boy(delivery_boy["id"])
    for o in my_orders:
        with st.container(border=True):
            order_items = db.get_order_items(o["id"])
            items_text = ", ".join(f"{oi['item_name']} x{oi['quantity']}" for oi in order_items)
            st.write(f"**Order #{o['id']}** — {items_text} — Status: **{o['status']}**")
            st.caption(f"Deliver to: {o['buyer_address']} | Phone: {o['buyer_phone']}")
            if o["status"] != "Delivered":
                if st.button("Mark as Delivered", key=f"delivered_{o['id']}"):
                    db.update_order_status(o["id"], "Delivered")
                    st.rerun()
    if not my_orders:
        st.caption("Aapne abhi tak koi order accept nahi kiya.")


def render_admin():
    st.markdown("""
    <div class="lm-banner" style="background: linear-gradient(90deg, #8e24aa 0%, #4a148c 100%);">
        <h1>🛠️ Admin Dashboard</h1>
        <p>Platform stats, approvals aur controls.</p>
    </div>
    """, unsafe_allow_html=True)
    ADMIN_PASSCODE = st.secrets.get("ADMIN_PASSCODE", "admin123")

    if "is_admin" not in st.session_state:
        st.session_state["is_admin"] = False

    if not st.session_state["is_admin"]:
        pw = st.text_input("Admin passcode", type="password", key="admin_pw")
        if st.button("Enter", key="admin_enter"):
            if pw == ADMIN_PASSCODE:
                st.session_state["is_admin"] = True
                st.rerun()
            else:
                st.error("Galat passcode.")
        return

    stats = db.get_admin_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Shops", stats["total_shops"])
    c2.metric("Total Orders", stats["total_orders"])
    c3.metric("Total Earning", f"₹{stats['total_platform_earning']}")
    st.write(f"Order commissions: ₹{stats['total_order_commission']}")
    st.write(f"Recharge commissions: ₹{stats['total_recharge_commission']}")

    st.divider()
    st.subheader("📈 Daily Orders & Revenue (last 14 days)")
    daily_stats = db.get_daily_order_stats(14)
    if daily_stats:
        df = pd.DataFrame(daily_stats).set_index("day")
        oc1, oc2 = st.columns(2)
        with oc1:
            st.caption("Orders per day")
            st.bar_chart(df["order_count"])
        with oc2:
            st.caption("Revenue per day (₹)")
            st.line_chart(df["revenue"])
    else:
        st.caption("Abhi charts ke liye enough data nahi hai.")

    st.divider()
    st.subheader("🏪 Shopkeepers — Approve / Ban")
    shops = db.get_all_shopkeepers_admin()
    for s in shops:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            status = "✅ Approved" if s["is_approved"] else "⏳ Pending"
            banned = " | 🚫 BANNED" if s["is_banned"] else ""
            c1.write(f"**{s['shop_name']}** ({s['owner_name']}, {s['phone']}) — {status}{banned}")
            c1.caption(f"Wallet: ₹{s['wallet_balance']}")
            if not s["is_approved"]:
                if c2.button("Approve", key=f"approve_{s['id']}"):
                    db.approve_shopkeeper(s["id"], True)
                    st.rerun()
            if not s["is_banned"]:
                if c3.button("Ban", key=f"ban_shop_{s['id']}"):
                    db.set_shopkeeper_ban(s["id"], True)
                    st.rerun()
            else:
                if c3.button("Unban", key=f"unban_shop_{s['id']}"):
                    db.set_shopkeeper_ban(s["id"], False)
                    st.rerun()

    st.divider()
    st.subheader("🛵 Delivery Boys — Ban")
    dboys = db.get_all_delivery_boys_admin()
    for d in dboys:
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            banned = " | 🚫 BANNED" if d["is_banned"] else ""
            c1.write(f"**{d['name']}** ({d['phone']}){banned}")
            if not d["is_banned"]:
                if c2.button("Ban", key=f"ban_d_{d['id']}"):
                    db.set_delivery_boy_ban(d["id"], True)
                    st.rerun()
            else:
                if c2.button("Unban", key=f"unban_d_{d['id']}"):
                    db.set_delivery_boy_ban(d["id"], False)
                    st.rerun()

    if st.button("Logout", key="admin_logout"):
        st.session_state["is_admin"] = False
        st.rerun()


if view == "Home":
    render_home()
elif view == "🛍️ Buyer":
    render_buyer()
elif view == "🏪 Shopkeeper":
    render_shopkeeper()
elif view == "🛵 Delivery Boy":
    render_delivery_boy()
elif view == "🛠️ Admin":
    render_admin()
