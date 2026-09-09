"""
utils.py - Helper functions: distance calculation, delivery charge slabs,
UPI QR code generation.
"""

import math
import io
import urllib.parse
import qrcode


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance between two lat/lng points, in kilometers."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calculate_delivery_charge(distance_km, subtotal=0, free_delivery_threshold=0):
    """
    Slab-based delivery charge:
      up to 1 km  -> Rs 20
      up to 2 km  -> Rs 30
      up to 3 km  -> Rs 40
      ... i.e. Rs 10 (base) + Rs 10 per started km
    If the shop has set a free_delivery_threshold > 0 and the order subtotal
    meets/exceeds it, delivery charge becomes 0 (shopkeeper's own choice).
    """
    if distance_km is None:
        return None
    km_slab = max(1, math.ceil(distance_km))  # round UP to next full km, min 1
    charge = 10 + (10 * km_slab)

    free_delivery_applied = bool(free_delivery_threshold and free_delivery_threshold > 0
                                  and subtotal >= free_delivery_threshold)
    if free_delivery_applied:
        charge = 0
    return charge, km_slab, free_delivery_applied


def estimate_delivery_time(distance_km):
    """
    Rough same-day delivery time estimate shown to the buyer, purely based on
    distance. Real ETA also depends on shopkeeper prep time and delivery boy
    availability - this is a friendly estimate, not a guarantee.
    """
    if distance_km is None:
        return "N/A"
    if distance_km <= 2:
        return "~30-45 min"
    elif distance_km <= 5:
        return "~45-60 min"
    elif distance_km <= 10:
        return "~1-2 hours"
    else:
        return "~2-3 hours"


def generate_upi_qr(upi_id, payee_name, amount, note="Order Payment"):
    """
    Returns a PIL Image containing a UPI-compatible QR code.
    Scanning this with any UPI app (GPay/PhonePe/Paytm) pre-fills the
    payee UPI ID and amount so the buyer just has to confirm & pay.
    """
    params = {
        "pa": upi_id,          # payee address (UPI ID)
        "pn": payee_name,      # payee name
        "am": f"{amount:.2f}", # amount
        "cu": "INR",
        "tn": note,
    }
    upi_url = "upi://pay?" + urllib.parse.urlencode(params)

    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img, upi_url


def image_to_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
