"""Realized sigma from yfinance (Yang-Zhang, 252-day annualization) applied to the measured pools."""
import json
import math
import re
import sys

import yfinance as yf

TRADING_DAYS = 252
S = sys.argv[1]


def yang_zhang(df):
    o, h, lo, c = (df[k].tolist() for k in ("Open", "High", "Low", "Close"))
    n = len(o) - 1
    on = [math.log(o[i] / c[i - 1]) for i in range(1, len(o))]
    oc = [math.log(c[i] / o[i]) for i in range(1, len(o))]
    rs = [math.log(h[i] / c[i]) * math.log(h[i] / o[i]) + math.log(lo[i] / c[i]) * math.log(lo[i] / o[i])
          for i in range(1, len(o))]
    var = lambda xs: sum((x - sum(xs) / n) ** 2 for x in xs) / (n - 1)
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    return math.sqrt((var(on) + k * var(oc) + (1 - k) * sum(rs) / n) * TRADING_DAYS)


def relative(stock, quote):
    joined = stock["Close"].to_frame("s").join(quote["Close"].to_frame("q"), how="inner").dropna()
    r = (joined["s"] / joined["q"]).tolist()
    lr = [math.log(r[i] / r[i - 1]) for i in range(1, len(r))]
    m = sum(lr) / len(lr)
    return math.sqrt(sum((x - m) ** 2 for x in lr) / (len(lr) - 1) * TRADING_DAYS), len(r)


def hist(t):
    df = yf.Ticker(t).history(period="3mo", interval="1d", auto_adjust=False)
    df.index = df.index.tz_localize(None).normalize()
    return df


rows = json.load(open(f"{S}/active_liq.json")) + json.load(open(f"{S}/active_liq_rh.json"))
cache = {}
QUOTE_STABLE = {"USDT", "USDG", "USDC"}
QUOTE_CRYPTO = {"WETH": "ETH-USD", "WBNB": "BNB-USD"}

print(f"{'pool':34} {'sigma':>6} {'IL':>6} {'APYfrm':>7} {'net_frm':>8} {'APYfr':>6} {'net_fr':>7} {'rich':>5}")
for r in rows:
    if r["vol24h"] < 1000:
        continue
    base, quote = [x.strip().split()[0] for x in r["pool"].split("/")]
    base = re.sub(r"(B|x)$", "", base, flags=re.I) if r["net"] == "bsc" else base
    base = base.upper()
    if base not in cache:
        cache[base] = hist(base)
    if quote.upper() in QUOTE_STABLE:
        sigma, kind = yang_zhang(cache[base]), "YZ"
    else:
        qt = QUOTE_CRYPTO[quote.upper()]
        if qt not in cache:
            cache[qt] = hist(qt)
        sigma, _ = relative(cache[base], cache[qt])
        kind = "rel"
    il = sigma**2 / 8
    r.update(sigma=sigma, il=il, net_formula=r["apy_formula"] - il, net_fullrange=r["apy_fullrange"] - il,
             richness=sigma / math.sqrt(8 * r["apy_fullrange"]), sigma_kind=kind, ticker=base)
    label = f"{r['net'][:2]} {r['pool']}"
    print(f"{label:34} {sigma*100:5.0f}% {il*100:5.1f}% {r['apy_formula']*100:6.1f}% {r['net_formula']*100:7.1f}% "
          f"{r['apy_fullrange']*100:5.1f}% {r['net_fullrange']*100:6.1f}% {r['richness']:5.2f} {kind}")

json.dump([r for r in rows if "sigma" in r], open(f"{S}/net_yield.json", "w"), indent=1)
