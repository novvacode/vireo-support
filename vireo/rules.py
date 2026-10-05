"""Stage 1 of the categoriser: deterministic text normalisation + keyword rules.

Input is ONLY the customer's opening message (never agent_notes). Returns, per message, the scores
for every category, the winning category, and a reason string naming the phrases that matched.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ------------------------------------------------------------------ normalisation

# Product names that contain issue words ("65W charger", "charging case", "cable") - removed so
# that buying a charger is not read as a charging fault.
PRODUCT_NAMES = (
    r"65 ?w (?:gan )?charge?r|gan charger|your charger|the charger|my charger|(?:spare|replacement|pulse) "
    r"(?:charging )?case|charging case(?: i ordered)?|spare case|usb-?c (?:braided )?cable|braided cable"
    r"|the cable|my cable|orbit (?:smart |mini )?speaker|mini speaker|orbit mini|speaker"
)
# Phrases customers append to ANY complaint. They say what the customer wants as a remedy, not what
# went wrong, so they must not drive the category (else everything becomes 'refund').
CLOSING_DEMANDS = (
    r"i (?:want|need) (?:a |my )?(?:replacement|refund|money back)(?: or (?:a )?(?:refund|replacement))?"
    r"|i want my money back|refund\.? now|replacement\.? now|i request you to [^.]*"
    r"|expected: ?\w+|fix this or i am posting[^.]*|escalate this to someone senior"
    r"|this is the last time i buy from you|please call me on my registered number"
    r"|kindly (?:do the needful|look into it)|please (?:help|advise|resolve asap|revert)"
    r"|need this sorted this week|not acceptable at this price|very poor quality"
    r"|honestly regretting this purchase|pathetic experience honestly|i am losing patience"
    r"|this is very disappointing|really frustrating|not what i expected from vireo"
    r"|i have been a loyal customer (?:&|and) this is how (?:u|you) treat me"
)
RULES_VERSION = "v2"  # v1 = frozen at validation experiment 1; v2 = post-test changes, see docs/validation.md
# v2: "Tried" steps ("I already checked the invoice", "I called the courier") describe what the customer did,
# not what went wrong; they caused v1 errors ("wrong product delivered. i checked the invoice" -> invoice).
# Kept deliberately narrow: stripping every "I tried/checked ..." step removed real evidence
# ("I checked mic permissions", "I checked the tracking page") and turned ~150 messages Unclear.
TRIED_STEPS = r"\bi (?:have |had )?(?:already )?(?:re)?che?c?ke?d (?:the |my )?(?:invoice|order)\b"
HINGLISH_FILLERS = (
    r"\b(?:bhai|sir ji|ji|kuch karo|bahut pareshan hu|itna paisa diya hai|abhi tak kuch nahi hua"
    r"|please jaldi|pls jaldi|jaldi|se|hello\?\?|anyone there|urgent|namaste)\b"
)
# common typos -> canonical spelling (applied word-wise)
TYPO = {
    r"\bdel[ei]+v[ea]?r(?:e|d|ed)?\b": "delivered", r"\bdelievre(?:d)?\b": "delivered", r"\bdlvr\w*": "delivery",
    r"\brec[ei]+v[e]?d\b": "received", r"\brecie?ved\b": "received", r"\breceivd\b": "received",
    r"\bcou?r[ie]+r\b": "courier", r"\bcouirer\b": "courier", r"\bcuorier\b": "courier",
    r"\bpa(?:a)?yment\b": "payment", r"\bpyment\b": "payment", r"\bdebt?[ie]+d\b": "debited",
    r"\bded[eu]?cted\b": "deducted", r"\brefnd\b|\breufnd\b|\brefnud\b": "refund",
    r"\binvo+ice\b|\binvoic\b": "invoice", r"\bwar+an+ty\b|\bwaranty\b": "warranty",
    r"\brepa+ir\b": "repair", r"\bbat+e?ry\b": "battery", r"\bchar+ging\b|\bcharrging\b": "charging",
    r"\bfirm?wa?e?r\b|\bfirmwaer\b": "firmware", r"\bupda?e\b|\bupdae\b": "update",
    r"\bwaiitng\b|\bwaitinng\b": "waiting", r"\bpackage\b|\bpakage\b|\bpcakage\b": "package",
    r"\bstatsu\b": "status", r"\bmicrophone\b": "mic", r"\breu?trn\b|\bretrun\b|\breutrn\b": "return",
}


def normalise(msg: str) -> str:
    s = str(msg).lower()
    s = s.replace("[ivr transcript]", " ")
    # structured template: keep the Issue line (it carries the need); drop Tried/Expected
    m = re.search(r"issue:\s*(.+?)(?:\s+tried:|\s+expected:|$)", s, flags=re.S)
    if m:
        s = m.group(1)
    s = re.sub(r"\s+", " ", s)
    for pat, rep in TYPO.items():
        s = re.sub(pat, rep, s)
    s = re.sub(CLOSING_DEMANDS, " ", s)
    s = re.sub(TRIED_STEPS, " ", s)
    s = re.sub(HINGLISH_FILLERS, " ", s)
    s = re.sub(PRODUCT_NAMES, " PRODUCT ", s)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ patterns
# weight 2 = phrase that on its own identifies the need; weight 1 = supporting word.

P = {
    "order_not_arrived": [
        (2, r"not (?:been )?delivered|haven'?t received (?:my|the) (?:order|item|parcel)|not received (?:my|the) (?:order|parcel)"
            r"|order not received|nothing in hand|empty handed|still waiting for (?:something|it|my order|the order) to show"
            r"|show up|nothing at my door|box never came|where is my (?:stuff|order|parcel)|item not with me"
            r"|marked it delivered|says? delivered but|out for delivery|stuck on shipped|status (?:has )?not moved"
            r"|still says processing|doorstep says otherwise|doo+rstep|no idea where it is|paid, confirmed, then nothing"
            r"|\d+ days\.? nothing|tracking (?:not updating|has said|page)|lost in transit|shipment not received"
            r"|package not delivered|parcel (?:stuck|not)|not arrived|hasn'?t arrived|never (?:came|arrived)(?! back)"),
        (1, r"tracking|courier|shipment|dispatch|delivery|parcel|package"),
    ],
    "damaged_or_wrong_item": [
        (2, r"damaged|crack|crushed|kicked|arrived broken|broken in the box|wrong (?:item|product|model|size|variant)"
            r"|not what i (?:paid for|ordered)|what'?s inside is not|missing from the box|empty box|seal (?:was )?broken"
            r"|before i (?:even )?switched it on|dented"
            r"|(?:got|received|delivered|sent)(?: me)? (?:a |the )?(?:different|wrong) colou?r|different colou?r than (?:i )?ordered"
            r"|ordered \w+,? (?:but )?got \w+|got \w+ instead|not what i asked for|got something else"
            r"|completely different (?:thing|product|item)"),
    ],
    "cancel_or_change": [
        (2, r"cancel|stop the shipment|don'?t ship|ordered by mistake|change of mind|wrong colou?r"
            r"|change (?:the |my )?(?:delivery |shipping )?address|update (?:my )?(?:shipping |delivery )?address"
            r"|wrong pin ?code|pin ?code|moved houses?|old flat|flat number|address"),
    ],
    "payment_issue": [
        (2, r"no order (?:was )?(?:created|id|confirmation)|got no order id|i have no orders|order not showing|nothing shows in my account"
            r"|page failed after i paid|upi shows success|app shows nothing|charged (?:two|2) times|charged twice|double (?:payment|charge|deducted)"
            r"|two entr\w+|same amount twice|paid once,? statement|statement disagrees|payment failed|failed payment"
            r"|deducted (?:but|without) (?:no )?order|debited but order not"),
        (1, r"debited|deducted|payment|paid|money (?:went|gone)|bank|upi|transaction|rs ?\d+ went"),
    ],
    "invoice_or_price": [
        (2, r"invoice|gst|tax bill|bill with|the bill|coupon|promo ?code|discount|offer vanished|% off|full price|price"),
    ],
    "return_pickup": [
        (2, r"pick ?up (?:scheduled|has not|not done|missed|pending)|nobody came for (?:the )?pick ?up|no one showed up"
            r"|waiting for your courier|reschedul\w+ pick ?up|return pick ?up|reverse pick ?up|nobody came"),
        (1, r"pick ?up"),
    ],
    "refund_not_received": [
        (2, r"refund (?:not|was promised|pending|delay|still)|still waiting for (?:my|the) refund|refund not received"
            r"|money for the return|money hasn'?t come back|amount is nowhere|return was accepted|refund status"
            r"|where is (?:my|the) refund|waiting for (?:my|the) refund|refund (?:hasn'?t|has not)"),
        (1, r"refund"),
    ],
    "warranty_status": [
        (2, r"warranty|repair|service cent(?:er|re)|sent the unit|\brma\b|claim"),
    ],
    "pairing_connection": [
        (2, r"pairing|\bpair(?:ed)? (?:with|it|them|to)|\b(?:can'?t|cannot|won'?t|not|doesn'?t) pair|bluetooth|disconnect|cutting out|keeps dropping|doesn'?t see it|not (?:showing|visible) in (?:the )?(?:list|bluetooth)"
            r"|device list|goes silent for a s\w+ every|every few minutes|wi-?fi|2\.4 ?ghz|hotspot|connecting screen|won'?t connect"
            r"|cannot connect|can'?t connect|not connecting|connects for a second"),
    ],
    "sound_or_hardware": [
        (2, r"no (?:audio|sound)|sound|audio|\bmic\b|can'?t hear|cannot hear me|hear (?:music )?in one ear|\bsilent\b|\bmute\b"
            r"|crackl|\bstatic\b|\bhiss|\bbuzz|volume|one (?:side|ear)|left side|right side|distort|screen (?:is )?unresponsive"
            r"|not responding to touch|does nothing when i touch|wen i touch|strap|button (?:not|doesn|stuck|broken)|won'?t turn on|doesn'?t turn on|dead on arrival"),
    ],
    "battery_charging": [
        (2, r"battery|(?<!card )charg(?!ed (?:two|2|twice))|drain|full to empty|dies? by|\b0 ?%|0 percent|percent|lasts? (?:only )?\d+ hours|paperweight"
            r"|lights up when i put|same battery level|dead every morning|backup"
            r"|promised \d+ hours|i get maybe \d+|used to last"),
    ],
    "app_firmware_login": [
        (2, r"firmware|(?:after|since) the (?:last )?update|update (?:is )?stuck|update failed|update prompt|stuck at \d+ ?%"
            r"|\botp\b|login|log in|code never arrives|sent me a code|locked out|my (?:own )?account|password"
            r"|white screen|loading screen|spinning circle|crash|app (?:not opening|won'?t open|shows a|just shows|closes)"),
        (1, r"\bapp\b|update"),
    ],
    "product_question": [
        (2, r"compatible|work (?:with|w/) (?:iphone|android|my|a|laptop|tv)|will (?:the|this|it|my) [\w ]{0,20}(?:run|work|survive)"
            r"|survive a shower|water ?proof|water resistant|can i connect|connect two|does [\w ]{1,20} work|old nokia"
            r"|how (?:do|to) (?:i )?use|is there (?:a|any)"),
    ],
}
COMPILED = {c: [(w, re.compile(p)) for w, p in pats] for c, pats in P.items()}


@dataclass
class RuleResult:
    category: str
    confidence: float
    scores: dict
    reason: str
    multi_issue: bool


def score(text: str) -> tuple[dict, dict]:
    sc, hits = {}, {}
    for cat, pats in COMPILED.items():
        s, h = 0, []
        for w, rx in pats:
            for m in rx.finditer(text):
                s += w
                h.append(m.group(0))
        if s:
            sc[cat], hits[cat] = s, h
    return sc, hits


def _strong(sc: dict, cat: str, hits: dict) -> bool:
    """True if `cat` matched at least one weight-2 phrase."""
    return sc.get(cat, 0) >= 2 and any(rx.search(" ".join(hits[cat])) for w, rx in COMPILED[cat] if w == 2)


def classify(message: str) -> RuleResult:
    text = normalise(message)
    sc, hits = score(text)
    strong = {c for c in sc if _strong(sc, c, hits)}

    def pick(cat, conf, why):
        multi = len(strong - {cat}) > 0
        return RuleResult(cat, conf, sc, f"{why}; matched: " + ", ".join(sorted(set(hits.get(cat, []))))[:200], multi)

    if not strong:
        return RuleResult("unclear", 0.0, sc, "no decisive phrase", False)

    # --- precedence for the known overlaps (documented in docs/validation.md) ---
    # 'paid ... still not here' is a delivery problem unless the customer says no order exists / double charge
    if "order_not_arrived" in strong and "payment_issue" in strong:
        return pick("order_not_arrived" if not re.search(r"no order|no orders|not showing|nothing shows|twice|two|double|statement", text)
                    else "payment_issue", 0.8, "precedence: paid-but-not-delivered vs payment")
    # pickup happened but money missing -> refund; pickup not happened -> pickup
    if "refund_not_received" in strong and "return_pickup" in strong:
        return pick("refund_not_received" if re.search(r"picked up|money|amount|refund", text) and not re.search(r"nobody came|no one showed", text)
                    else "return_pickup", 0.8, "precedence: refund vs pickup")
    # cancelling/changing before delivery beats generic delivery words ('stop the shipment')
    if "cancel_or_change" in strong and strong & {"order_not_arrived", "damaged_or_wrong_item"}:
        if re.search(r"cancel|stop the shipment|don'?t ship|ordered by mistake|change of mind|wrong colou?r|address|pin ?code|moved", text):
            return pick("cancel_or_change", 0.8, "precedence: cancel/change before delivery")
    # warranty claim/repair status beats the fault description inside it
    if "warranty_status" in strong and re.search(r"status|update on|heard nothing|no update|sent the unit|service cent", text):
        return pick("warranty_status", 0.8, "precedence: repair/claim status")
    # battery wording beats 'app shows 0%' and 'left one dead'
    if "battery_charging" in strong and strong & {"app_firmware_login", "sound_or_hardware"} and re.search(r"charg|battery|0 ?%|percent|drain", text):
        return pick("battery_charging", 0.8, "precedence: battery/charging wording")
    # firmware/update wording beats 'pairing light' etc. only when update is the subject
    if "app_firmware_login" in strong and "pairing_connection" in strong and re.search(r"firmware|update|app crash|loading screen", text):
        return pick("app_firmware_login", 0.8, "precedence: app/firmware")
    # 'goes silent every few minutes' is a dropout, not a sound fault
    if "pairing_connection" in strong and "sound_or_hardware" in strong and re.search(r"every few minutes|for a s\w+|disconnect|cutting out|drops", text):
        return pick("pairing_connection", 0.8, "precedence: dropout")
    # a refund for a double charge belongs with the payment problem (owner decision 2)
    if "payment_issue" in strong and "refund_not_received" in strong:
        return pick("payment_issue", 0.8, "precedence: refund for a payment problem")

    if len(strong) == 1:
        (c,) = strong
        return pick(c, 0.95, "single rule")
    best = sorted(strong, key=lambda c: -sc[c])
    if sc[best[0]] > sc[best[1]]:
        return pick(best[0], 0.6, "highest rule score among several")
    return RuleResult("unclear", 0.3, sc, "tie between " + ", ".join(best[:2]), True)
