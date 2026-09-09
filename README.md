# LocalMarket — Hyperlocal Marketplace MVP

Ek Streamlit app jisme:
- **Buyer** kisi bhi delivery address (apne shehar ya kisi doosre shehar/ghar) ke liye,
  us address ke sabse nazdeek shopkeepers se koi bhi cheez order kar sakta hai
- **Shopkeeper** apna stock (brand, specifications, photo, unit-wise price) list karta hai,
  wallet recharge karta hai, orders manage karta hai, free-delivery threshold set karta hai
- **Delivery Boy** orders accept karke deliver karta hai (ya shopkeeper khud bhej sakta hai)
- **Admin** platform stats, charts, shopkeeper approval/ban dekh sakta hai

Payment seedha shopkeeper ke UPI ID par jata hai (QR code se). Platform commission:
- Wallet **recharge** par 2% (edit karo `db.py` mein `RECHARGE_COMMISSION_PERCENT`)
- Har **order** par 2% (edit karo `db.py` mein `ORDER_COMMISSION_PERCENT`)
- Minimum recharge ₹100 (edit karo `db.py` mein `MIN_RECHARGE_AMOUNT`)
- Delivery charge slab: ₹10 + ₹10 per km, shopkeeper free-delivery threshold set kar sakta hai
  (edit karo `utils.py` mein `calculate_delivery_charge`)

## ✨ Features
- **Buyer login/signup zaroori** — bina account ke search/order nahi kar sakte (jaise Amazon/Flipkart)
- Colorful, modern e-commerce-style design (original — koi bhi brand ka logo/asset copy nahi kiya)
- Alag delivery location (current location se bhi, aur kisi doosre shehar/address ke liye bhi)
- Item: brand, specifications, **Main Category + Sub-category** (comprehensive built-in list — Electronics
  se lekar bike, saree, needle tak sab kuch; "Other" bhi hamesha available hai), unit (piece/gram/kg/ml/litre), photo
- Search filters: category, brand, price range
- Cart (ek shop ke multiple items ek order mein)
- Estimated delivery time (distance ke hisaab se)
- Order history + ratings/reviews (shop aur delivery boy dono ke liye)
- Low-stock alerts, bulk CSV item upload (`sample_bulk_items.csv` dekho)
- Wallet low-balance warning
- Delivery boy: earnings summary (today/total), delivery history
- Admin: approve/ban shopkeepers, ban delivery boys, daily orders/revenue charts

## 🔜 Abhi tak add nahi hua (external account chahiye)
- **OTP login** — SMS bhejne ke liye Twilio/MSG91 jaisi service ka paid account chahiye
- **Real payment verification** — Razorpay/Cashfree jaisa payment gateway account chahiye
  (abhi QR scan ke baad payment manually confirm karni padti hai)

---

## 1. Apne computer par test karna (optional)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Browser mein `http://localhost:8501` khul jayega.

---

## 2. GitHub par code daalna

Agar pehli baar GitHub use kar rahe ho:

1. https://github.com par account banao (agar nahi hai)
2. Naya repository banao (top-right `+` → **New repository**) — naam do jaise `local-market-mvp`, **Public** rakho, "Add README" ko UNCHECK rakho (kyunki hamare paas already hai)
3. Apne computer/terminal mein is folder ke andar jaake ye commands chalao:

```bash
cd local-market-mvp
git init
git add .
git commit -m "Initial commit - LocalMarket MVP"
git branch -M main
git remote add origin https://github.com/<aapka-username>/local-market-mvp.git
git push -u origin main
```

(`<aapka-username>` ki jagah apna GitHub username daalo. Pehli baar push karte waqt GitHub login maang sakta hai — Personal Access Token banana pad sakta hai: GitHub → Settings → Developer settings → Personal access tokens.)

---

## 3. Streamlit Community Cloud par deploy karna (FREE)

1. https://share.streamlit.io par jao aur apne GitHub account se sign in karo
2. **"Create app"** ya **"New app"** button dabao
3. Apni repository select karo (`local-market-mvp`)
4. Branch: `main`, Main file path: `app.py`
5. **"Deploy"** dabao — 1-2 minute mein aapka app live ho jayega, ek URL milega jaise:
   `https://<something>.streamlit.app`

Bas! Ye link kisi ke saath bhi share kar sakte ho.

### Admin passcode set karna (recommended)
Deploy hone ke baad app ke **Settings → Secrets** mein jaake ye add karo:
```
ADMIN_PASSCODE = "apna-secret-passcode"
```
(Nahi kiya to default `admin123` use hoga — production mein zaroor badlo.)

---

## ⚠️ Important limitations (MVP hai, production nahi)

1. **Database aur images reset ho sakte hain**: Streamlit Cloud free tier par `market.db` (SQLite) aur `uploaded_images/` permanently persist nahi hote — app restart/redeploy hone par data reset ho sakta hai. Real launch se pehle isse **Supabase (Postgres)** + cloud storage (S3/Cloudinary) mein migrate karna.
2. **Payment verification manual hai**: QR scan hone ke baad system ko pata nahi chalta ki payment actually hui ya nahi. Real app ke liye **Razorpay/Cashfree UPI payment gateway** integrate karna hoga.
3. **Location accuracy**: Auto-detect browser permission maangta hai; agar user deny kare to manual lat/lng dalna padta hai.
4. **Security**: Password hashing basic hai (SHA-256). Production ke liye proper auth (bcrypt + salt, ya Firebase Auth / Supabase Auth) use karo. OTP login abhi implement nahi hai.
5. **Scale**: Streamlit ek chhoti app ke liye perfect hai (hundreds of users). Lakhs of users ke liye aage chalke proper backend (FastAPI/Django + mobile app) chahiye hoga.

---

## Files (single-page app — koi page-switch flicker nahi)
```
local-market-mvp/
├── app.py                    # SAB KUCH ek hi file mein (Home + Buyer + Shopkeeper + Delivery Boy + Admin)
├── db.py                     # Database (SQLite) + business logic
├── utils.py                  # Distance, delivery charge, ETA, UPI QR
├── requirements.txt
├── sample_bulk_items.csv     # Bulk item upload ka example format
├── uploaded_images/          # Shopkeeper item photos yahan save hoti hain
└── README.md
```

