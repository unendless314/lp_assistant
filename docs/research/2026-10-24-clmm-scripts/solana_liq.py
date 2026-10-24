"""Read active liquidity from Raydium CLMM / Orca Whirlpool accounts; validate decoding via price."""
import base64
import json
import sys
import time
import urllib.request

GT = "https://api.geckoterminal.com/api/v2"
RPC = "https://api.mainnet-beta.solana.com"
RAYDIUM_CLMM = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
ORCA_WHIRLPOOL = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
UA = {"User-Agent": "lp-assistant-research"}

POOLS = [
    "8aDaBQkTrS6HVMjyc6EZebgdiaXhLYGriDWKWWp1NpFF", "HHQUnUbmWLrYzkscDY1C3deEFbGtiGBGoHjpANogmvum",
    "9p7abUFv31ycgu9kckvnoqMMvBy67dqTDM2m6HP9xokN", "6FQQyf7UcyU86TZC1cmAcfC4a18SJyDggEKtQfTJWmfs",
    "49iMatQtoyabsYAQc8GafVq6aeBFVDxSRH44oiatyyw6", "6R4r93V5fcMzc13CL2enEepDSYcr4Qx3ptZBDwudTXCo",
    "38rXq2BuwdNcfnwydw6S2srpNK9N4gVzf39f69suPMsF", "8Vy5Rjb9vg5nLb8L1r4Di8p9py5BTkp8UJSMHG8AD2zs",
    "4pCZCVEiYyT4efNdXUdL2tJF8VGMgiMXrZWq6FiNXhRw", "6truu3rZuiB9rKQg4VYC3Dt3QwV7DgwGqXrYUcrvnDDE",
    "Fae5dWVntUt6zbWu2voXxioDpMii7SqQwtsxBmoVCsHR", "FCn5zw4gAcfRpQgst5ThFuzBGXbbJ6RocVErgC4vJ9j1",
]


def http_json(url, body=None):
    headers = dict(UA, **({"Content-Type": "application/json"} if body else {}))
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=headers)
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


def account(addr):
    v = http_json(RPC, {"jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                        "params": [addr, {"encoding": "base64"}]})["result"]["value"]
    return v["owner"], base64.b64decode(v["data"][0])


def b58(raw):
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    n = int.from_bytes(raw, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = alphabet[r] + s
    return "1" * (len(raw) - len(raw.lstrip(b"\0"))) + s


u = lambda d, o, n: int.from_bytes(d[o:o + n], "little")


def decode(owner, d):
    if owner == RAYDIUM_CLMM:
        _, cfg = account(b58(d[9:41]))
        return {"mint_a": b58(d[73:105]), "mint_b": b58(d[105:137]), "dec_a": d[233], "dec_b": d[234],
                "liquidity": u(d, 237, 16), "sqrt_q64": u(d, 253, 16), "fee": u(cfg, 47, 4) / 1e6}
    if owner == ORCA_WHIRLPOOL:
        mint_a, mint_b = b58(d[101:133]), b58(d[181:213])
        return {"mint_a": mint_a, "mint_b": mint_b, "dec_a": account(mint_a)[1][44], "dec_b": account(mint_b)[1][44],
                "liquidity": u(d, 49, 16), "sqrt_q64": u(d, 65, 16), "fee": u(d, 45, 2) / 1e6}
    return None


rows = []
for addr in POOLS:
    p = http_json(f"{GT}/networks/solana/pools/{addr}")["data"]
    a = p["attributes"]
    tvl, vol = float(a["reserve_in_usd"]), float(a["volume_usd"]["h24"])
    rel = p["relationships"]
    prices = {rel["base_token"]["data"]["id"].split("_", 1)[1]: float(a["base_token_price_usd"]),
              rel["quote_token"]["data"]["id"].split("_", 1)[1]: float(a["quote_token_price_usd"])}
    owner, data = account(addr)
    dex = rel["dex"]["data"]["id"]
    s = decode(owner, data)
    if s is None:
        print(f"{dex:13} {a['name']:16} owner {owner} -- unsupported layout")
        time.sleep(2.5)
        continue
    sqrt_p = s["sqrt_q64"] / 2**64
    price_b_per_a = sqrt_p**2 * 10 ** (s["dec_a"] - s["dec_b"])
    gt_price_b_per_a = prices[s["mint_a"]] / prices[s["mint_b"]]
    active_usd = 2 * s["liquidity"] * sqrt_p / 10 ** s["dec_b"] * prices[s["mint_b"]]
    r = {"net": "solana", "dex": dex, "pool": a["name"], "addr": addr, "fee": s["fee"], "tvl": tvl, "vol24h": vol,
         "active_fullrange_equiv_usd": active_usd, "M_eff": active_usd / tvl,
         "apy_formula": vol * s["fee"] / tvl * 365, "apy_fullrange": vol * s["fee"] / active_usd * 365,
         "price_check": price_b_per_a / gt_price_b_per_a}
    rows.append(r)
    print(f"{dex:13} {a['name']:16} fee {s['fee']*100:5.2f}% TVL {tvl/1e3:6.0f}k vol {vol/1e3:6.0f}k "
          f"price-check {r['price_check']:.3f}  M_eff {r['M_eff']:6.2f}  APY formula {r['apy_formula']*100:6.1f}%  "
          f"full-range {r['apy_fullrange']*100:5.1f}%", flush=True)
    time.sleep(2.5)

json.dump(rows, open(sys.argv[1], "w"), indent=1)
