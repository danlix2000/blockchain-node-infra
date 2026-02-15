#!/usr/bin/env python3
"""
Avalanche / EVM block-lag & latency monitor (JSON-RPC)

What it does
------------
For a configured *group* of RPC endpoints (from endpoints.json), this tool:
- polls the latest block repeatedly for N seconds
- measures:
  - RPC latency (ms) for eth_getBlockByNumber("latest")
  - block lag (seconds): (wall clock now) - (latest block timestamp)
  - ETA to reach a target lag threshold (default <= 5s), using a windowed trend

Why ChainList is useful here
----------------------------
Avalanche C-Chain is one chainId (43114 / 43113), but in practice you may point this script
at "Avalanche based" EVM networks / subnets / L1s where chainId differs.

Instead of maintaining a huge static mapping, we can enrich chain name using ChainList:
- Source: https://chainlist.org/rpcs.json
- Cached locally (compact mapping) with TTL
- Optional (can disable)

Usage
-----
    python3 avax_blocklag.py avalanche-c
    python3 avax_blocklag.py avalanche-c --duration 60 --rate 0.2
    python3 avax_blocklag.py avalanche-c --config /etc/nodes/endpoints.json

    # More smoothing for ETA (more samples)
    python3 avax_blocklag.py avalanche-c --eta-window 60

    # Change “synced” threshold used for ETA
    python3 avax_blocklag.py avalanche-c --target-lag 10

ChainList options
-----------------
    # Disable ChainList lookup (use only the small built-in map)
    python3 avax_blocklag.py avalanche-c --no-chainlist

    # If ChainList fetch fails, still use stale cached mapping (if present)
    python3 avax_blocklag.py avalanche-c --chainlist-allow-stale

NetId diagnostics (optional)
----------------------------
ChainId != NetworkId is possible on some networks.
NetId column is OFF by default for clean output.

Enable NetId column:
    python3 avax_blocklag.py avalanche-c --show-netid

Config file format (endpoints.json)
-----------------------------------
{
  "avalanche-c": {
    "avax-node-1": "http://127.0.0.1:9650/ext/bc/C/rpc",
    "avax-node-2": "http://10.0.0.12:9650/ext/bc/C/rpc"
  }
}

POA / extraData fix
-------------------
Some EVM networks (including Avalanche) can return extraData length that triggers:
    "The field extraData is 90 bytes, but should be 32 ..."

Inject a POA/extraData middleware that works across web3.py versions.
"""

import argparse
import json
import logging
import math
import pathlib
import threading
import time
import urllib.error
import urllib.request
from typing import Dict, List, Tuple, Union, Optional

from web3 import Web3

# ─────────── POA middleware import (web3.py 5.x & 6.x+) ───────────
try:
    # web3.py <= 5.x
    from web3.middleware import geth_poa_middleware as poa_middleware
except Exception:
    # web3.py >= 6.x
    from web3.middleware import ExtraDataToPOAMiddleware as poa_middleware


LOG = logging.getLogger("avax_blocklag")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ────────── ChainList cache/config ──────────
DEFAULT_CHAINLIST_URL = "https://chainlist.org/rpcs.json"
DEFAULT_CHAINLIST_TTL_S = 24 * 60 * 60  # 24h
DEFAULT_CHAINLIST_CACHE = pathlib.Path.home() / ".cache" / \
    "avax_blocklag_chainlist_names.json"

# Populated at runtime (if enabled)
CHAINLIST_NAME_BY_ID: Dict[int, str] = {}


def _fetch_json_with_retries(
    url: str,
    timeout_s: int,
    retries: int,
    backoff_base_s: float,
) -> object:
    """
    Fetch JSON with exponential backoff retries.
    retries=2 => up to 3 attempts total.
    """
    last_err: Optional[Exception] = None
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "avax-blocklag/1.0"})
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read()
            return json.loads(raw.decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < attempts:
                sleep_s = backoff_base_s * (2 ** (attempt - 1))
                LOG.debug("ChainList fetch attempt %d/%d failed: %s (sleep %.2fs)",
                          attempt, attempts, e, sleep_s)
                time.sleep(sleep_s)
    assert last_err is not None
    raise last_err


def _build_chainid_to_name(payload: object) -> Dict[int, str]:
    """
    ChainList rpcs.json is typically a list of chain objects with chainId and name fields.
    We keep parsing defensive in case schema changes.
    """
    out: Dict[int, str] = {}

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            cid = item.get("chainId")
            name = item.get("name") or item.get(
                "chain") or item.get("shortName")
            if isinstance(cid, int) and isinstance(name, str) and name.strip():
                out[cid] = name.strip()
            elif isinstance(cid, str) and cid.isdigit() and isinstance(name, str) and name.strip():
                out[int(cid)] = name.strip()
        return out

    if isinstance(payload, dict):
        for key in ("chains", "data", "result"):
            maybe = payload.get(key)
            if isinstance(maybe, list):
                return _build_chainid_to_name(maybe)

    return out


def load_chainlist_name_map(
    url: str,
    cache_path: pathlib.Path,
    ttl_s: int,
    timeout_s: int,
    retries: int,
    backoff_base_s: float,
    allow_stale_cache: bool,
) -> Dict[int, str]:
    """
    Cache format:
    {
      "source": "<url>",
      "fetched_at": 1700000000,
      "ttl": 86400,
      "data": { "1": "Ethereum Mainnet", ... }
    }
    """
    cached_map: Dict[int, str] = {}
    cached_fetched_at: Optional[int] = None
    cached_ttl: Optional[int] = None

    # Read cache (even if stale; we may use it if the network fetch fails)
    try:
        if cache_path.exists():
            cache_obj = json.loads(cache_path.read_text())
            if isinstance(cache_obj, dict) and isinstance(cache_obj.get("data"), dict):
                data = cache_obj["data"]
                cached_map = {
                    int(k): str(v).strip()
                    for k, v in data.items()
                    if str(k).isdigit() and isinstance(v, str) and str(v).strip()
                }

                fa = cache_obj.get("fetched_at")
                if isinstance(fa, (int, float)) or (isinstance(fa, str) and fa.isdigit()):
                    cached_fetched_at = int(fa)

                ct = cache_obj.get("ttl")
                if isinstance(ct, (int, float)) or (isinstance(ct, str) and ct.isdigit()):
                    cached_ttl = int(ct)
    except Exception as e:
        LOG.debug("ChainList cache read skipped: %s", e)

    # If cache is fresh, return it
    if cached_map and cached_fetched_at is not None:
        effective_ttl = cached_ttl if cached_ttl is not None else ttl_s
        age = int(time.time()) - int(cached_fetched_at)
        if age <= effective_ttl:
            return cached_map

    # Otherwise fetch
    try:
        payload = _fetch_json_with_retries(
            url=url, timeout_s=timeout_s, retries=retries, backoff_base_s=backoff_base_s)
        mapping = _build_chainid_to_name(payload)

        if mapping:
            try:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_obj = {
                    "source": url,
                    "fetched_at": int(time.time()),
                    "ttl": int(ttl_s),
                    "data": {str(k): v for k, v in mapping.items()},
                }
                cache_path.write_text(json.dumps(cache_obj))
            except Exception as e:
                LOG.debug("ChainList cache write skipped: %s", e)

        return mapping
    except Exception as e:
        if allow_stale_cache and cached_map:
            LOG.warning(
                "ChainList fetch failed (%s): %s - using stale cache (%s).", url, e, cache_path)
            return cached_map
        LOG.warning(
            "ChainList fetch failed (%s): %s - chain names may show as Unknown.", url, e)
        return {}


def seconds_to_human_readable(seconds: Union[int, float]) -> str:
    if isinstance(seconds, float) and (math.isinf(seconds) or math.isnan(seconds)):
        return "∞"
    total = int(seconds)
    if total < 0:
        total = 0
    days, rem = divmod(total, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m {secs}s"
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def chain_name_from_id(chain_id: Optional[int]) -> str:
    """
    Prefer ChainList dynamic mapping (if loaded), else small static fallback.
    """
    if isinstance(chain_id, int) and chain_id in CHAINLIST_NAME_BY_ID:
        return CHAINLIST_NAME_BY_ID[chain_id]

    # Minimal Avalanche-focused fallback
    mapping = {
        43114: "Avalanche C-Chain Mainnet",
        43113: "Avalanche Fuji Testnet",
        # common extras
        1: "Ethereum Mainnet",
        5: "Goerli",
        11155111: "Sepolia",
    }
    if chain_id is None:
        return "Unknown"
    return mapping.get(chain_id, "Unknown")


def safe_client_version(w3: Web3) -> str:
    try:
        return w3.clientVersion  # web3.py 5.x
    except Exception:
        try:
            return w3.client_version  # web3.py 6.x+
        except Exception:
            return "N/A"


def _rpc_make_request(w3: Web3, method: str, params: list) -> Optional[dict]:
    try:
        provider = getattr(w3, "provider", None)
        if provider is None or not hasattr(provider, "make_request"):
            return None
        # type: ignore[attr-defined]
        resp = provider.make_request(method, params)
        return resp if isinstance(resp, dict) else None
    except Exception:
        return None


def get_chain_id(w3: Web3) -> Optional[int]:
    """
    Professional stance: only trust eth_chainId for chainId.
    Do NOT guess chainId from net_version (network id).
    """
    try:
        return int(w3.eth.chain_id)
    except Exception:
        pass

    resp = _rpc_make_request(w3, "eth_chainId", [])
    if resp:
        val = resp.get("result")
        if isinstance(val, str) and val.startswith("0x"):
            try:
                return int(val, 16)
            except Exception:
                return None
    return None


def get_network_id(w3: Web3) -> Optional[int]:
    """
    NetworkId (net_version) used only when --show-netid for diagnostics.
    Not guaranteed equal to chainId.
    """
    resp = _rpc_make_request(w3, "net_version", [])
    if resp:
        val = resp.get("result")
        if isinstance(val, str) and val.isdigit():
            return int(val)
    return None


def format_chain_id(chain_id: Optional[int]) -> str:
    if isinstance(chain_id, int):
        return f"{chain_id} / {hex(chain_id)}"
    return "N/A"


class AvaxMonitor:
    """
    Thread-safe aggregator for per-endpoint metrics.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        self.total_elapsed: Dict[str, float] = {}
        self.total_requests: Dict[str, int] = {}

        self.total_lag: Dict[str, float] = {}
        self.total_blocks: Dict[str, int] = {}

        # store (sample_ts, lag_seconds)
        self.lag_history: Dict[str, List[Tuple[float, int]]] = {}

        self.client_versions: Dict[str, str] = {}
        self.chain_id_int: Dict[str, Optional[int]] = {}
        self.chain_names: Dict[str, str] = {}
        self.latest_blocks: Dict[str, int] = {}
        # only meaningful if --show-netid
        self.network_ids: Dict[str, Optional[int]] = {}

    def set_metadata(self, endpoint: str, version: str, chain_id: Optional[int], chain_name: str, network_id: Optional[int]) -> None:
        with self._lock:
            self.client_versions[endpoint] = version
            self.chain_id_int[endpoint] = chain_id
            self.chain_names[endpoint] = chain_name
            self.network_ids[endpoint] = network_id

    def update(self, endpoint: str, sample_ts: float, elapsed: float, lag: int, block_number: int) -> None:
        with self._lock:
            self.total_elapsed.setdefault(endpoint, 0.0)
            self.total_requests.setdefault(endpoint, 0)
            self.total_lag.setdefault(endpoint, 0.0)
            self.total_blocks.setdefault(endpoint, 0)
            self.lag_history.setdefault(endpoint, [])

            self.total_elapsed[endpoint] += elapsed
            self.total_requests[endpoint] += 1
            self.total_lag[endpoint] += lag
            self.total_blocks[endpoint] += 1

            self.lag_history[endpoint].append((sample_ts, lag))
            # keep bounded
            if len(self.lag_history[endpoint]) > 10_000:
                self.lag_history[endpoint] = self.lag_history[endpoint][-10_000:]

            self.latest_blocks[endpoint] = block_number

    def avg_latency_ms(self, endpoint: str) -> float:
        with self._lock:
            req = self.total_requests.get(endpoint, 0)
            if not req:
                return 0.0
            return (self.total_elapsed[endpoint] / req) * 1000.0

    def avg_block_lag_seconds(self, endpoint: str) -> float:
        with self._lock:
            cnt = self.total_blocks.get(endpoint, 0)
            if not cnt:
                return 0.0
            return self.total_lag[endpoint] / cnt

    def estimate_sync_time(self, endpoint: str, target_lag_s: int, window_samples: int) -> Union[str, float]:
        """
        Estimate ETA to reach <= target_lag_s.

        Uses recent samples (window_samples):
        - compute slope of lag over time
        - if lag is decreasing, estimate time to hit target
        """
        with self._lock:
            hist = list(self.lag_history.get(endpoint, []))

        if len(hist) < 3:
            return "Not enough data"

        points = hist[-window_samples:] if len(hist) > window_samples else hist
        cur_lag = points[-1][1]

        if cur_lag <= target_lag_s:
            return "SYNCED"

        t_first, lag_first = points[0]
        t_last, lag_last = points[-1]
        dt = t_last - t_first
        if dt <= 0:
            return "Not enough data"

        slope = (lag_last - lag_first) / dt  # lag seconds per wall second
        if slope >= 0:
            return "Lag stable/increasing"

        remaining = cur_lag - target_lag_s
        rate = -slope
        return remaining / rate if rate > 0 else float("inf")


def make_w3(url: str, timeout: int = 10) -> Web3:
    """
    Create a Web3 client and inject PoA/extraData middleware for compatibility.
    """
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": timeout}))
    try:
        w3.middleware_onion.inject(poa_middleware, layer=0)
    except Exception:
        # Safe fallback (don't fail creation if middleware injection fails)
        pass
    return w3


def poll_latest_block(w3: Web3, name: str, rate: float, stop: float, monitor: AvaxMonitor) -> None:
    while time.time() < stop:
        try:
            t0 = time.time()
            block = w3.eth.get_block("latest", False)
            t1 = time.time()
            elapsed = t1 - t0

            block_ts = int(block["timestamp"])
            lag = max(0, int(t1) - block_ts)
            block_no = int(block["number"])

            monitor.update(name, sample_ts=t1, elapsed=elapsed,
                           lag=lag, block_number=block_no)

            LOG.debug("[%s] block=%s latency=%.2fms lag=%s", name,
                      block_no, elapsed * 1000.0, seconds_to_human_readable(lag))
        except Exception as e:
            LOG.warning("[%s] RPC polling failed: %s", name, str(e))
        time.sleep(rate)


def run(
    endpoints: Dict[str, str],
    duration: int,
    rate: float,
    target_lag_s: int,
    eta_window_samples: int,
    show_netid: bool,
    use_chainlist: bool,
    chainlist_url: str,
    chainlist_cache: pathlib.Path,
    chainlist_ttl: int,
    chainlist_timeout: int,
    chainlist_retries: int,
    chainlist_backoff: float,
    chainlist_allow_stale: bool,
) -> None:
    stop = time.time() + duration
    monitor = AvaxMonitor()
    threads: List[threading.Thread] = []
    failed: Dict[str, str] = {}

    # Load ChainList chainId->name map once (cached + TTL)
    if use_chainlist:
        global CHAINLIST_NAME_BY_ID
        CHAINLIST_NAME_BY_ID = load_chainlist_name_map(
            url=chainlist_url,
            cache_path=chainlist_cache,
            ttl_s=chainlist_ttl,
            timeout_s=chainlist_timeout,
            retries=chainlist_retries,
            backoff_base_s=chainlist_backoff,
            allow_stale_cache=chainlist_allow_stale,
        )
        if CHAINLIST_NAME_BY_ID:
            LOG.info("Loaded %d chain names from ChainList (cache/API).",
                     len(CHAINLIST_NAME_BY_ID))

    for name, url in endpoints.items():
        try:
            w3 = make_w3(url, timeout=10)

            # quick connectivity test
            _ = w3.eth.block_number

            ver = safe_client_version(w3)
            chain_id = get_chain_id(w3)
            chain_name = chain_name_from_id(chain_id)
            net_id = get_network_id(w3) if show_netid else None

            monitor.set_metadata(name, ver, chain_id, chain_name, net_id)

            t = threading.Thread(target=poll_latest_block, args=(
                w3, name, rate, stop, monitor), daemon=True)
            t.start()
            threads.append(t)

        except Exception as e:
            LOG.warning(
                "[%s] Skipping due to connection issue: %s", name, str(e))
            failed[name] = str(e)

    for t in threads:
        t.join()

    LOG.info("Average metrics after the test completes:")

    hdr = (
        f"{'Endpoint':<34}"
        f"{'AvgLatency (ms)':>15} "
        f"{'AvgBlockLag':>12} "
        f"{f'ETA<={target_lag_s}s':>16} "
        f"{'Block':>12} "
        f"{'ChainId':>18} "
        f"{'Chain':<28} "
    )
    if show_netid:
        hdr += f"{'NetId':>8} "
    hdr += "Client Version"

    LOG.info(hdr)
    LOG.info("=" * len(hdr))

    for name in endpoints:
        if name in failed:
            row = (
                f"[{name:<31}] {'N/A':>15} {'N/A':>12} {'Connection Failed':>16} "
                f"{'N/A':>12} {'N/A':>18} {'Unknown':<28} "
            )
            if show_netid:
                row += f"{'N/A':>8} "
            row += "N/A"
            LOG.info(row)
            continue

        lat = monitor.avg_latency_ms(name)
        lag_s = monitor.avg_block_lag_seconds(name)
        lag_str = seconds_to_human_readable(lag_s)

        eta = monitor.estimate_sync_time(
            name, target_lag_s=target_lag_s, window_samples=eta_window_samples)
        eta_str = seconds_to_human_readable(
            eta) if isinstance(eta, (int, float)) else eta

        blk = monitor.latest_blocks.get(name, 0)
        chain_id = monitor.chain_id_int.get(name)
        chain_id_disp = format_chain_id(chain_id)
        chain_name = monitor.chain_names.get(name, "Unknown")
        ver = monitor.client_versions.get(name, "N/A")

        row = (
            f"[{name:<31}] {lat:>15.2f} {lag_str:>12} {eta_str:>16} "
            f"{blk:>12} {chain_id_disp:>18} {chain_name:<28} "
        )

        if show_netid:
            net_id = monitor.network_ids.get(name)
            net_id_str = str(net_id) if isinstance(net_id, int) else "N/A"
            row += f"{net_id_str:>8} "

        row += ver
        LOG.info(row)


def load_endpoints(group: str, config_path: pathlib.Path) -> Dict[str, str]:
    try:
        data = json.loads(config_path.read_text())
    except FileNotFoundError as exc:
        raise SystemExit(f"Config file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {config_path}: {exc}") from exc

    if group not in data:
        raise SystemExit(f"No group '{group}' in {config_path}")
    if not isinstance(data[group], dict) or not data[group]:
        raise SystemExit(
            f"Group '{group}' is empty or invalid in {config_path}")

    # Ensure name->url strings
    out: Dict[str, str] = {}
    for k, v in data[group].items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out


def cli() -> None:
    default_cfg = pathlib.Path(__file__).with_name("endpoints.json")

    p = argparse.ArgumentParser(
        description="Monitor Avalanche/EVM block-lag & latency for a group of RPC endpoints.")
    p.add_argument(
        "group", help="Group name in endpoints.json, e.g. avalanche-c")
    p.add_argument("--duration", "-d", type=int, default=30,
                   help="Test length in seconds (default: 30)")
    p.add_argument("--rate", "-r", type=float, default=0.20,
                   help="Delay between RPC calls in seconds (default: 0.20)")
    p.add_argument("--target-lag", type=int, default=5,
                   help="ETA target lag in seconds (default: 5)")
    p.add_argument("--eta-window", type=int, default=20,
                   help="Number of recent samples for ETA smoothing (default: 20)")
    p.add_argument(
        "--config",
        "-c",
        type=pathlib.Path,
        default=default_cfg,
        help=f"Path to endpoints.json (default: {default_cfg})",
    )

    # Diagnostics
    p.add_argument(
        "--show-netid",
        action="store_true",
        help="Show net_version (Network ID) column for diagnostics. Not guaranteed equal to chainId.",
    )

    # ChainList options
    p.add_argument(
        "--no-chainlist",
        action="store_true",
        help="Disable ChainList lookup for chain names (uses only the small built-in map).",
    )
    p.add_argument(
        "--chainlist-url",
        default=DEFAULT_CHAINLIST_URL,
        help=f"ChainList API URL (default: {DEFAULT_CHAINLIST_URL})",
    )
    p.add_argument(
        "--chainlist-ttl",
        type=int,
        default=DEFAULT_CHAINLIST_TTL_S,
        help="ChainList cache TTL seconds (default: 86400).",
    )
    p.add_argument(
        "--chainlist-cache",
        type=pathlib.Path,
        default=DEFAULT_CHAINLIST_CACHE,
        help=f"Path to ChainList cache file (default: {DEFAULT_CHAINLIST_CACHE}).",
    )
    p.add_argument(
        "--chainlist-timeout",
        type=int,
        default=15,
        help="ChainList fetch timeout seconds (default: 15).",
    )
    p.add_argument(
        "--chainlist-retries",
        type=int,
        default=2,
        help="ChainList fetch retries (default: 2).",
    )
    p.add_argument(
        "--chainlist-backoff",
        type=float,
        default=0.5,
        help="ChainList retry backoff base seconds (default: 0.5).",
    )
    p.add_argument(
        "--chainlist-allow-stale",
        action="store_true",
        help="If ChainList fetch fails, use stale cache if present.",
    )

    args = p.parse_args()

    LOG.info("Loading endpoints from %s (group=%s)", args.config, args.group)
    endpoints = load_endpoints(args.group, args.config)

    LOG.info("Testing for %s s at one call every %.2f s …",
             args.duration, args.rate)
    run(
        endpoints=endpoints,
        duration=args.duration,
        rate=args.rate,
        target_lag_s=args.target_lag,
        eta_window_samples=args.eta_window,
        show_netid=args.show_netid,
        use_chainlist=(not args.no_chainlist),
        chainlist_url=args.chainlist_url,
        chainlist_cache=args.chainlist_cache,
        chainlist_ttl=args.chainlist_ttl,
        chainlist_timeout=args.chainlist_timeout,
        chainlist_retries=args.chainlist_retries,
        chainlist_backoff=args.chainlist_backoff,
        chainlist_allow_stale=args.chainlist_allow_stale,
    )


if __name__ == "__main__":
    cli()
