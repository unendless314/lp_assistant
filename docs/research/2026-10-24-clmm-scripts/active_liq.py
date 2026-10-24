"""Compare formula APY (vol*fee/TVL) vs full-range-equivalent APY (vol*fee / 2L*sqrtP) for V3 pools."""
import json
import re
import sys
import time
import urllib.request

GT = "https://api.geckoterminal.com/api/v2"
RPC = {
    "bsc": "https://bsc-dataseed.binance.org",
    "robinhood": "https://rpc.mainnet.chain.robinhood.com",
}
SEL = {"liquidity": "0x1a686502", "slot0": "0x3850c7bd", "token0": "0x0dfe1681",
       "token1": "0xd21220a7", "decimals": "0x313ce567", "fee": "0xddca3f43"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "lp-assistant-research"})
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(15)
                continue
            raise
    raise RuntimeError("rate limited")


def call(net, to, sel):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": to, "data": sel}, "latest"]}).encode()
    req = urllib.request.Request(RPC[net], data=body, headers={"Content-Type": "application/json", "User-Agent": "lp-assistant-research"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    if "result" not in res:
        raise RuntimeError(res)
    return res["result"]


def word(hexstr, i=0):
    h = hexstr[2:]
    return int(h[64 * i:64 * (i + 1)], 16)


def analyze(net, addr):
    p = get(f"{GT}/networks/{net}/pools/{addr}")["data"]
    a = p["attributes"]
    tvl = float(a["reserve_in_usd"])
    vol = float(a["volume_usd"]["h24"])
    base_addr = p["relationships"]["base_token"]["data"]["id"].split("_", 1)[1].lower()
    prices = {base_addr: float(a["base_token_price_usd"])}
    quote_addr = p["relationships"]["quote_token"]["data"]["id"].split("_", 1)[1].lower()
    prices[quote_addr] = float(a["quote_token_price_usd"])

    fee_raw = word(call(net, addr, SEL["fee"]))  # hundredths of a bip: 2500 = 0.25%
    fee = fee_raw / 1_000_000
    liq = word(call(net, addr, SEL["liquidity"]))
    sqrt_x96 = word(call(net, addr, SEL["slot0"]))
    t1 = "0x" + call(net, addr, SEL["token1"])[-40:]
    dec1 = word(call(net, t1, SEL["decimals"]))

    sqrt_p = sqrt_x96 / 2**96  # sqrt(token1_raw / token0_raw)
    active_fullrange_usd = 2 * liq * sqrt_p / 10**dec1 * prices[t1.lower()]

    apy_formula = vol * fee / tvl * 365
    apy_fullrange = vol * fee / active_fullrange_usd * 365
    return {
        "pool": a["name"], "dex": p["relationships"]["dex"]["data"]["id"], "net": net,
        "fee": fee, "tvl": tvl, "vol24h": vol,
        "active_fullrange_equiv_usd": active_fullrange_usd,
        "M_eff": active_fullrange_usd / tvl,
        "apy_formula": apy_formula, "apy_fullrange": apy_fullrange,
    }


def find(net, query, n=3):
    d = get(f"{GT}/search/pools?query={query}&network={net}")["data"]
    out = []
    for p in d:
        dex = p["relationships"]["dex"]["data"]["id"]
        if re.search(r"v3|uniswap-bsc", dex) and "v4" not in dex and float(p["attributes"]["reserve_in_usd"]) > 30_000:
            out.append(p["attributes"]["address"])
    return out[:n]


if __name__ == "__main__":
    targets = [("robinhood", q) for q in ("NVDA", "CRCL", "SPY", "USO")]
    rows = []
    for net, q in targets:
        try:
            addrs = find(net, q)
        except Exception as e:
            print("search fail", net, q, e, file=sys.stderr)
            continue
        for addr in addrs:
            try:
                r = analyze(net, addr)
                r["addr"] = addr
                rows.append(r)
                print(f"{r['net']:9} {r['dex']:22} {r['pool']:28} TVL {r['tvl']/1e3:8.0f}k vol {r['vol24h']/1e3:7.0f}k "
                      f"M_eff {r['M_eff']:6.2f}  APY formula {r['apy_formula']*100:7.1f}%  full-range {r['apy_fullrange']*100:6.1f}%",
                      flush=True)
            except Exception as e:
                print("fail", net, addr, e, file=sys.stderr)
            time.sleep(2.5)
    json.dump(rows, open(sys.argv[1] if len(sys.argv) > 1 else "active_liq.json", "w"), indent=1)
