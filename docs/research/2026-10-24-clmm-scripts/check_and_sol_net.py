import json, math, sys, time, urllib.request
sys.path.insert(0, sys.argv[1])
S = sys.argv[1]
import active_liq as A
import yfinance as yf
# 1) EVM price check on a few pools
for net, addr in [("bsc", "0xb0f5e5400e8f0f7c242f2b7740c004f020579c41"), ("bsc", "0x613ebcfcf41749571d659a0bf3e2c0032fd4859e"),
                  ("robinhood", "0xd4eb21209c4d6093f80b5b84f5c45cc093ea14a3")]:
    p = A.get(f"{A.GT}/networks/{net}/pools/{addr}")["data"]; a = p["attributes"]; rel = p["relationships"]
    prices = {rel["base_token"]["data"]["id"].split("_", 1)[1].lower(): float(a["base_token_price_usd"]),
              rel["quote_token"]["data"]["id"].split("_", 1)[1].lower(): float(a["quote_token_price_usd"])}
    t0 = "0x" + A.call(net, addr, A.SEL["token0"])[-40:]; t1 = "0x" + A.call(net, addr, A.SEL["token1"])[-40:]
    d0 = A.word(A.call(net, t0, A.SEL["decimals"])); d1 = A.word(A.call(net, t1, A.SEL["decimals"]))
    sp = A.word(A.call(net, addr, A.SEL["slot0"])) / 2**96
    onchain = sp**2 * 10**(d0 - d1); gt = prices[t0] / prices[t1]
    print(f"price-check {net} {a['name']}: {onchain/gt:.3f}")
    time.sleep(2.5)
# 2) Solana net yield
def hist(t):
    df = yf.Ticker(t).history(period="3mo", interval="1d", auto_adjust=False); df.index = df.index.tz_localize(None).normalize(); return df
def yz(df):
    o,h,lo,c = (df[k].tolist() for k in ("Open","High","Low","Close")); n=len(o)-1
    on=[math.log(o[i]/c[i-1]) for i in range(1,len(o))]; oc=[math.log(c[i]/o[i]) for i in range(1,len(o))]
    rs=[math.log(h[i]/c[i])*math.log(h[i]/o[i])+math.log(lo[i]/c[i])*math.log(lo[i]/o[i]) for i in range(1,len(o))]
    var=lambda xs: sum((x-sum(xs)/n)**2 for x in xs)/(n-1); k=0.34/(1.34+(n+1)/(n-1))
    return math.sqrt((var(on)+k*var(oc)+(1-k)*sum(rs)/n)*252)
def rel(s, q):
    j = s["Close"].to_frame("s").join(q["Close"].to_frame("q"), how="inner").dropna(); r=(j["s"]/j["q"]).tolist()
    lr=[math.log(r[i]/r[i-1]) for i in range(1,len(r))]; m=sum(lr)/len(lr)
    return math.sqrt(sum((x-m)**2 for x in lr)/(len(lr)-1)*252)
rows = json.load(open(f"{S}/active_liq_sol.json")); cache = {}
for r in rows:
    base, quote = [x.strip() for x in r["pool"].split("/")]; t = base.rstrip("x")
    cache.setdefault(t, hist(t))
    if quote == "SOL":
        cache.setdefault("SOL-USD", hist("SOL-USD")); sigma = rel(cache[t], cache["SOL-USD"])
    else:
        sigma = yz(cache[t])
    il = sigma**2/8
    r.update(sigma=sigma, il=il, net_formula=r["apy_formula"]-il, net_fullrange=r["apy_fullrange"]-il,
             richness=sigma/math.sqrt(8*r["apy_fullrange"]))
    print(f"so {r['dex']:12} {r['pool']:14} fee {r['fee']*100:4.2f}% sigma {sigma*100:3.0f}% IL {il*100:4.1f}% "
          f"net_formula {r['net_formula']*100:6.1f}% net_fullrange {r['net_fullrange']*100:5.1f}% rich {r['richness']:.2f}")
json.dump(rows, open(f"{S}/net_yield_sol.json", "w"), indent=1)
