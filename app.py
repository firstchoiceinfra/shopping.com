"""
app.py - Single-page LocalMarket app.

Sab kuch ek hi page mein hai (Buyer / Shopkeeper / Delivery Boy / Admin) -
sidebar se sirf 'view' switch hota hai, koi alag page load nahi hota,
isliye Streamlit ka default multi-page navigation flicker nahi aata.
"""

import streamlit as st
import db
from utils import haversine_km, calculate_delivery_charge, generate_upi_qr, image_to_bytes

st.set_page_config(page_title="LocalMarket", page_icon="🛒", layout="centered")
db.init_db()

if "view" not in st.session_state:
    st.session_state["view"] = "Home"

with st.sidebar:
    st.title("🛒 LocalMarket")
    view = st.radio(
        "Role choose karo",
        ["Home", "🛍️ Buyer", "🏪 Shopkeeper", "🛵 Delivery Boy", "🛠️ Admin"],
        index=["Home", "🛍️ Buyer", "🏪 Shopkeeper", "🛵 Delivery Boy", "🛠️ Admin"].index(st.session_state["view"])
    )
    st.session_state["view"] = view


def render_home():
    st.title("🛒 LocalMarket")
    st.caption("Har cheez, sabse nazdeek dukaandaar se — seedha aapke ghar tak.")
    st.markdown("""
Ye ek **hyperlocal marketplace MVP** hai jisme:
- 🛍️ **Buyer** apne aas-paas ke dukaandaaron se koi bhi cheez order kar sakta hai
- 🏪 **Shopkeeper** apna stock list kar sakta hai aur orders receive kar sakta hai
- 🛵 **Delivery Boy** orders accept karke deliver kar sakta hai

Payment seedha shopkeeper ke UPI par jata hai — platform sirf **1% commission** per order
aur wallet recharge par **2% commission** leta hai.

👈 **Left sidebar** se apna role choose karo.
""")


def render_buyer():
    st.title("🛍️ Buyer - Kuch bhi order karo")

    st.subheader("📍 Apna location set karo")
    try:
        from streamlit_js_eval import get_geolocation
        if st.button("📡 Auto-detect location", key="buyer_gps"):
            loc = get_geolocation()
            if loc and "coords" in loc:
                st.session_state["buyer_lat"] = loc["coords"]["latitude"]
                st.session_state["buyer_lng"] = loc["coords"]["longitude"]
                st.success("Location detect ho gayi!")
    except Exception:
        st.caption("(Auto-detect deploy hone ke baad kaam karega. Abhi manually daal sakte ho.)")

    c1, c2 = st.columns(2)
    lat = c1.number_input("Latitude", value=st.session_state.get("buyer_lat", 28.6139), format="%.6f", key="buyer_lat_input")
    lng = c2.number_input("Longitude", value=st.session_state.get("buyer_lng", 77.2090), format="%.6f", key="buyer_lng_input")
    st.session_state["buyer_lat"] = lat
    st.session_state["buyer_lng"] = lng

    buyer_address = st.text_input("Delivery address (house no, street, landmark)", key="buyer_address")

    st.divider()
    st.subheader("🔍 Item dhoondo")
    query = st.text_input("Kya chahiye? (e.g. 'atta', 'phone charger', 'milk')", key="buyer_query")

    if query:
        results = db.search_items_with_shop(query)
        if not results:
            st.warning("Koi shopkeeper nahi mila jo ye item bech raha ho abhi. Baad mein try karo.")
        else:
            for r in results:
                r["distance_km"] = haversine_km(lat, lng, r["latitude"], r["longitude"])
            results = [r for r in results if r["distance_km"] is not None]
            results.sort(key=lambda r: r["distance_km"])

            st.write(f"**{len(results)} shopkeeper(s)** mile jo '{query}' bechte hain — nazdeek se door:")

            for r in results:
                charge, km_slab = calculate_delivery_charge(r["distance_km"])
                total = round(r["price"] + charge, 2)
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.markdown(f"**🏪 {r['shop_name']}**")
                        st.write(f"{r['item_name']} — ₹{r['price']}")
                        st.caption(f"📍 {r['distance_km']:.2f} km door | Stock: {r['stock_qty']}")
                    with c2:
                        st.metric("Delivery", f"₹{charge}")
                    st.write(f"**Total: ₹{total}** (item ₹{r['price']} + delivery ₹{charge})")

                    if not r["upi_id"]:
                        st.caption("⚠️ Ye shopkeeper ne abhi UPI ID add nahi ki — order place nahi ho sakta.")
                    else:
                        order_key = f"order_{r['item_id']}_{r['shopkeeper_id']}"
                        if st.button(f"Order karo — {r['shop_name']}", key=order_key):
                            st.session_state["pending_order"] = {**r, "delivery_charge": charge, "total": total}

    if "pending_order" in st.session_state:
        po = st.session_state["pending_order"]
        st.divider()
        st.subheader("✅ Order confirm karo")
        with st.form("confirm_order_form"):
            buyer_name = st.text_input("Aapka naam")
            buyer_phone = st.text_input("Aapka phone number")
            qty = st.number_input("Quantity", min_value=1, value=1, step=1)
            submitted = st.form_submit_button("Order place karo aur QR dikhao")

        if submitted:
            if not buyer_name or not buyer_phone or not buyer_address:
                st.error("Naam, phone aur address bharna zaroori hai.")
            else:
                item_total = round(po["price"] * qty, 2)
                grand_total = round(item_total + po["delivery_charge"], 2)
                commission, new_balance = db.deduct_order_commission(po["shopkeeper_id"], grand_total)

                order_id = db.create_order(
                    buyer_name=buyer_name, buyer_phone=buyer_phone,
                    buyer_lat=lat, buyer_lng=lng, buyer_address=buyer_address,
                    shopkeeper_id=po["shopkeeper_id"], item_id=po["item_id"], item_name=po["item_name"],
                    quantity=qty, item_price=po["price"], distance_km=po["distance_km"],
                    delivery_charge=po["delivery_charge"], total_amount=grand_total,
                    commission_amount=commission
                )

                st.success(f"🎉 Order #{order_id} place ho gaya!")
                st.write(f"**Total pay karna hai: ₹{grand_total}** seedha shopkeeper ko.")

                qr_img, upi_url = generate_upi_qr(po["upi_id"], po["shop_name"], grand_total, note=f"Order #{order_id}")
                st.image(image_to_bytes(qr_img), caption="Is QR ko scan karke UPI se payment karo", width=250)
                st.caption(upi_url)
                del st.session_state["pending_order"]


def render_shopkeeper():
    st.title("🏪 Shopkeeper Panel")

    if "shop_id" not in st.session_state:
        tab_login, tab_signup = st.tabs(["Login", "Naya Account Banao"])

        with tab_login:
            phone = st.text_input("Phone number", key="s_login_phone")
            password = st.text_input("Password", type="password", key="s_login_pw")
            if st.button("Login", key="s_login_btn"):
                shop = db.authenticate_shopkeeper(phone, password)
                if shop:
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
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"Namaste, {shop['owner_name']} 👋 ({shop['shop_name']})")
    with col2:
        if st.button("Logout", key="s_logout"):
            del st.session_state["shop_id"]
            st.rerun()

    balance = shop["wallet_balance"]
    if balance <= 0:
        st.error(f"⚠️ Wallet balance: ₹{balance:.2f} — Aapki listing PUBLISH NAHI hai. Recharge karo.")
    else:
        st.success(f"💰 Wallet balance: ₹{balance:.2f} — Aapki listing LIVE hai.")

    tabs = st.tabs(["💰 Wallet", "📦 Items", "📍 Shop Details", "🧾 Orders"])

    with tabs[0]:
        st.write(f"Platform recharge par **{db.RECHARGE_COMMISSION_PERCENT}%** commission leta hai, baaki wallet mein credit.")
        st.write(f"Har order par wallet se **{db.ORDER_COMMISSION_PERCENT}%** commission auto-deduct hota hai.")
        amount = st.number_input("Recharge amount (₹)", min_value=10.0, value=100.0, step=10.0, key="recharge_amt")
        if st.button("Recharge karo (demo payment)", key="recharge_btn"):
            platform_cut, credited, new_balance = db.recharge_wallet(shop["id"], amount)
            st.success(f"₹{amount} recharge hua. Platform cut: ₹{platform_cut}, Credit: ₹{credited}. Naya balance: ₹{new_balance}")
            st.rerun()

        st.markdown("**Wallet History**")
        history = db.get_wallet_history(shop["id"])
        if history:
            st.dataframe(history, use_container_width=True, hide_index=True)
        else:
            st.caption("Abhi koi transaction nahi hui.")

    with tabs[1]:
        st.markdown("**Naya item add karo**")
        with st.form("add_item_form", clear_on_submit=True):
            item_name = st.text_input("Item ka naam")
            price = st.number_input("Price (₹)", min_value=1.0, value=10.0, step=1.0)
            stock_qty = st.number_input("Stock quantity", min_value=0, value=10, step=1)
            add_submitted = st.form_submit_button("Add karo")
        if add_submitted:
            if item_name:
                db.add_item(shop["id"], item_name, price, stock_qty)
                st.success(f"'{item_name}' add ho gaya!")
                st.rerun()
            else:
                st.error("Item ka naam daalo.")

        st.markdown("**Aapke items**")
        items = db.get_items_for_shop(shop["id"])
        if not items:
            st.caption("Abhi koi item add nahi kiya.")
        for it in items:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
                c1.write(f"**{it['item_name']}**")
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

    with tabs[3]:
        orders = db.get_orders_for_shop(shop["id"])
        if not orders:
            st.caption("Abhi koi order nahi aaya.")
        delivery_boys = db.get_available_delivery_boys()
        db_options = {f"{d['name']} ({d['phone']})": d["id"] for d in delivery_boys}

        for o in orders:
            with st.container(border=True):
                st.write(f"**Order #{o['id']}** — {o['item_name']} x{o['quantity']} — Status: **{o['status']}**")
                st.caption(f"Buyer: {o['buyer_name']} | {o['buyer_phone']} | {o['buyer_address']}")
                st.caption(f"Distance: {o['distance_km']:.2f} km | Delivery: ₹{o['delivery_charge']} | "
                           f"Total: ₹{o['total_amount']} | Commission: ₹{o['commission_amount']}")
                c1, c2 = st.columns(2)
                with c1:
                    status_options = ["Placed", "Preparing", "Out for Delivery", "Delivered", "Cancelled"]
                    new_status = st.selectbox("Status update karo", status_options,
                                               index=status_options.index(o["status"]), key=f"status_{o['id']}")
                    if st.button("Status save karo", key=f"save_status_{o['id']}"):
                        db.update_order_status(o["id"], new_status)
                        st.rerun()
                with c2:
                    if db_options:
                        chosen = st.selectbox("Delivery boy assign karo", list(db_options.keys()), key=f"db_{o['id']}")
                        if st.button("Assign karo", key=f"assign_{o['id']}"):
                            db.assign_delivery_boy_to_order(o["id"], db_options[chosen])
                            st.rerun()
                    else:
                        st.caption("Koi delivery boy available nahi — khud deliver karo.")


def render_delivery_boy():
    st.title("🛵 Delivery Boy Panel")

    if "delivery_id" not in st.session_state:
        tab_login, tab_signup = st.tabs(["Login", "Naya Account Banao"])
        with tab_login:
            phone = st.text_input("Phone number", key="d_login_phone")
            password = st.text_input("Password", type="password", key="d_login_pw")
            if st.button("Login", key="d_login_btn"):
                d = db.authenticate_delivery_boy(phone, password)
                if d:
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

    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"Namaste, {delivery_boy['name']} 👋")
    with col2:
        if st.button("Logout", key="d_logout"):
            del st.session_state["delivery_id"]
            st.rerun()

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
            st.write(f"**Order #{o['id']}** — {o['item_name']} x{o['quantity']}")
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
            st.write(f"**Order #{o['id']}** — {o['item_name']} x{o['quantity']} — Status: **{o['status']}**")
            st.caption(f"Deliver to: {o['buyer_address']} | Phone: {o['buyer_phone']}")
            if o["status"] != "Delivered":
                if st.button("Mark as Delivered", key=f"delivered_{o['id']}"):
                    db.update_order_status(o["id"], "Delivered")
                    st.rerun()
    if not my_orders:
        st.caption("Aapne abhi tak koi order accept nahi kiya.")


def render_admin():
    st.title("🛠️ Admin Dashboard")
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
    conn = db.get_connection()
    st.markdown("**All Shopkeepers**")
    shops = [dict(r) for r in conn.execute(
        "SELECT id, shop_name, owner_name, phone, wallet_balance, latitude, longitude FROM shopkeepers"
    ).fetchall()]
    st.dataframe(shops, use_container_width=True, hide_index=True)

    st.markdown("**All Orders**")
    orders = [dict(r) for r in conn.execute(
        "SELECT id, item_name, quantity, total_amount, commission_amount, status, created_at FROM orders ORDER BY id DESC"
    ).fetchall()]
    st.dataframe(orders, use_container_width=True, hide_index=True)
    conn.close()

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
