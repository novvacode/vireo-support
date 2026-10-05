"""The approved 13-category taxonomy (+ Unclear), owners, and how the intake bot's tags map onto it."""
from __future__ import annotations

FRONTLINE = "Frontline"  # resolved to Chat / Email / Voice Frontline by channel

CATEGORIES = {
    "order_not_arrived": ("Order not arrived", "Logistics",
                          "Paid order hasn't reached the customer: delayed, stuck tracking, marked delivered but not received"),
    "damaged_or_wrong_item": ("Damaged or wrong item received", "Logistics",
                              "It arrived, but broken / crushed / not what was ordered"),
    "cancel_or_change": ("Cancel or change an order", FRONTLINE,
                         "Stop, cancel or modify an order before delivery (change of mind, wrong colour, address/pincode)"),
    "payment_issue": ("Payment taken, no order / charged twice", "Billing",
                      "Money left the account but no order was created, payment page failed, or duplicate charge"),
    "invoice_or_price": ("Invoice, GST or price/discount", "Billing",
                         "Needs a bill / GST invoice, or a coupon/price was wrong at checkout"),
    "return_pickup": ("Return pickup not done", "Returns Desk", "Agreed return pickup didn't happen"),
    "refund_not_received": ("Refund not received", "Returns Desk",
                            "A promised refund hasn't arrived (usually after a return)"),
    "warranty_status": ("Warranty or repair status", "Escalations & Warranty",
                        "Unit already with service / claim open; customer wants an update"),
    "pairing_connection": ("Pairing & connection", FRONTLINE,
                           "Won't pair, drops out, not visible to phone, Wi-Fi setup"),
    "sound_or_hardware": ("Sound, mic or hardware fault", FRONTLINE,
                          "Device faulty in use: one side silent, mic low, crackle, screen unresponsive"),
    "battery_charging": ("Battery & charging", FRONTLINE,
                         "Drains fast, won't charge, one bud doesn't charge in case"),
    "app_firmware_login": ("App, firmware or login", FRONTLINE,
                           "App crashes / won't load, firmware update stuck, OTP / login code never arrives"),
    "product_question": ("Product question", FRONTLINE,
                         "Pre-sales or how-to: compatibility, water resistance, 'will it work with...'"),
    "unclear": ("Unclear", FRONTLINE, "Too little text to tell"),
}
LABELS = list(CATEGORIES)
NAME = {k: v[0] for k, v in CATEGORIES.items()}
OWNER = {k: v[1] for k, v in CATEGORIES.items()}

CHANNEL_FRONTLINE = {"chat": "Chat Frontline", "social": "Chat Frontline",
                     "email": "Email Frontline", "voice": "Voice Frontline"}

# Which new categories each bot tag is "compatible" with. A bot tag outside this set = disagreement.
# "Other" is compatible with nothing (a catch-all says nothing about the need).
BOT_COMPATIBLE = {
    "Billing & Payments": {"payment_issue", "invoice_or_price"},
    "Delivery & Shipping": {"order_not_arrived", "damaged_or_wrong_item"},
    "Returns & Refunds": {"return_pickup", "refund_not_received"},
    "Warranty & Repair": {"warranty_status"},
    "Connectivity": {"pairing_connection"},
    "Audio Quality": {"sound_or_hardware"},
    "Charging & Battery": {"battery_charging"},
    "App & Firmware": {"app_firmware_login"},
    "Account & Login": {"app_firmware_login"},
    "Product Enquiry": {"product_question"},
    "Other": set(),
}


def owner_team(category: str, channel: str) -> str:
    """Concrete owning team: Frontline categories resolve to the channel's Frontline team."""
    o = OWNER[category]
    return CHANNEL_FRONTLINE.get(channel, "Chat Frontline") if o == FRONTLINE else o
