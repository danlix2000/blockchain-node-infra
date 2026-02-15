#!/usr/bin/env python3
"""
Block Lag & Latency Monitor (multi-endpoint)

What it does
------------
For a configured *group* of RPC endpoints (from endpoints.json), this tool:
- polls latest block repeatedly for N seconds
- measures:
  - RPC latency (ms) for eth_getBlockByNumber("latest")
  - block lag (seconds): (wall clock now) - (latest block timestamp)
  - ETA to catch up (best-effort): estimated time until block-lag reaches ~0
    based on a windowed trend (default 30s)

Usage
-----
    python3 blocklag_monitor.py <group>
    python3 blocklag_monitor.py eth-sepolia
    python3 blocklag_monitor.py eth-main --duration 60 --rate 0.2
    python3 blocklag_monitor.py bnb-archive --eta-window 120

Config file (endpoints.json)
----------------------------
A JSON object where each key is a group name and the value is a dict of endpointName->url.

Example:
{
  "eth-sepolia": {
    "eth-us-east-1": "http://127.0.0.1:8545",
    "eth-us-east-public": "https://sepolia.infura.io/v3/xxxx"
  }
}

Chain name enrichment (ChainList)
---------------------------------
Some of your "Unknown" chain names happen because the built-in static mapping is small.
This script can optionally load chainId -> chain name from ChainList:

- Source: https://chainlist.org/rpcs.json
- Cached locally as a compact mapping file (default):
    ~/.cache/blocklag_monitor_chainlist_names.json
- TTL controls how often we refresh the cache (default 24h)

Disable ChainList:
    python3 blocklag_monitor.py <group> --no-chainlist

Use stale cache if ChainList fetch fails:
    python3 blocklag_monitor.py <group> --chainlist-allow-stale

NetId (network id) diagnostics
------------------------------
ChainId and NetworkId (net_version) are related but not guaranteed identical.
For a clean default output, NetId is OFF by default.

Enable NetId column (diagnostics):
    python3 blocklag_monitor.py <group> --show-netid

Exit codes
----------
- 0 always (this is a monitoring/reporting tool). If you want thresholds + non-zero exits,
  we can add --max-lag / --max-latency / --fail-on-unknown, etc.
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

# PoA middleware import differences across web3 versions
try:
    # web3 < 7
    from web3.middleware import geth_poa_middleware  # type: ignore
except Exception:  # pragma: no cover
    geth_poa_middleware = None  # type: ignore


# ────────────── logging ──────────────
LOG = logging.getLogger("blocklag_monitor")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# ────────── ChainList cache/config ──────────
DEFAULT_CHAINLIST_URL = "https://chainlist.org/rpcs.json"
DEFAULT_CHAINLIST_TTL_S = 24 * 60 * 60  # 24h
DEFAULT_CHAINLIST_CACHE = pathlib.Path.home() / ".cache" / \
    "blocklag_monitor_chainlist_names.json"

# Populated at runtime (if enabled)
CHAINLIST_NAME_BY_ID: Dict[int, str] = {}


def _fetch_json_with_retries(
    url: str,
    timeout_s: int,
    retries: int,
    backoff_base_s: float,
) -> object:
    """
    Fetch JSON with small exponential backoff retries.
    retries=2 -> up to 3 total attempts.
    """
    last_err: Optional[Exception] = None
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "blocklag-monitor/1.0"})
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
    ChainList rpcs.json is typically: [ { chainId: <int>, name: <str>, ... }, ... ]
    Be defensive in case schema changes.
    """
    out: Dict[int, str] = {}

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue

            cid = item.get("chainId")
            # Prefer a human-friendly name field
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

    # Read cache (even if stale; we may use it if network fetch fails)
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

    # If cache is fresh enough, return it
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


# ────────── helpers ──────────
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


def chain_name_from_chain_id(chain_id: Optional[int]) -> str:
    """
    Prefer ChainList dynamic mapping (if loaded), else small static fallback.
    """
    if isinstance(chain_id, int) and chain_id in CHAINLIST_NAME_BY_ID:
        return CHAINLIST_NAME_BY_ID[chain_id]

    static = {
        1: "Ethereum Mainnet",
        5: "Goerli",
        11155111: "Sepolia",
        56: "BNB Smart Chain",
        97: "BNB Testnet",
        137: "Polygon Mainnet",
        80001: "Mumbai",
        43114: "Avalanche C-Chain",
        43113: "Avalanche Fuji",
        10: "Optimism",
        8453: "Base",
        42161: "Arbitrum One",
        42170: "Arbitrum Nova",
        421614: "Arbitrum Sepolia",
    }
    if chain_id is None:
        return "Unknown"
    return static.get(chain_id, "Unknown")


# ────────────── monitor ───────────────
class LatencyMonitor:
    """
    Thread-safe aggregator.

    We update from multiple worker threads, so all shared state is protected with a lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        self.total_elapsed: Dict[str, float] = {}
        self.total_requests: Dict[str, int] = {}

        self.total_lag_seconds: Dict[str, float] = {}
        self.total_blocks: Dict[str, int] = {}

        # store (timestamp_of_sample, lag_seconds, block_number)
        self.lag_history: Dict[str, List[Tuple[float, int, int]]] = {}

        self.client_versions: Dict[str, str] = {}
        self.chain_ids: Dict[str, Optional[int]] = {}
        # only filled when --show-netid
        self.network_ids: Dict[str, Optional[int]] = {}
        self.chain_names: Dict[str, str] = {}
        self.last_block_numbers: Dict[str, int] = {}

    def set_client_version(self, endpoint: str, version: str) -> None:
        with self._lock:
            self.client_versions[endpoint] = version

    def set_chain(self, endpoint: str, chain_id: Optional[int], network_id: Optional[int]) -> None:
        with self._lock:
            self.chain_ids[endpoint] = chain_id
            self.network_ids[endpoint] = network_id
            self.chain_names[endpoint] = chain_name_from_chain_id(chain_id)

    def update(self, endpoint: str, sample_ts: float, elapsed: float, lag_seconds: int, block_number: int) -> None:
        with self._lock:
            self.total_elapsed.setdefault(endpoint, 0.0)
            self.total_requests.setdefault(endpoint, 0)

            self.total_lag_seconds.setdefault(endpoint, 0.0)
            self.total_blocks.setdefault(endpoint, 0)

            self.lag_history.setdefault(endpoint, [])
            self.last_block_numbers[endpoint] = block_number

            self.total_elapsed[endpoint] += elapsed
            self.total_requests[endpoint] += 1

            self.total_lag_seconds[endpoint] += lag_seconds
            self.total_blocks[endpoint] += 1

            self.lag_history[endpoint].append(
                (sample_ts, lag_seconds, block_number))

            # Bound history to avoid unbounded growth on long runs
            if len(self.lag_history[endpoint]) > 10_000:
                self.lag_history[endpoint] = self.lag_history[endpoint][-10_000:]

    def avg_latency_ms(self, endpoint: str) -> float:
        with self._lock:
            if not self.total_requests.get(endpoint):
                return 0.0
            return (self.total_elapsed[endpoint] / self.total_requests[endpoint]) * 1000.0

    def avg_block_lag_seconds(self, endpoint: str) -> float:
        with self._lock:
            if not self.total_blocks.get(endpoint):
                return 0.0
            return self.total_lag_seconds[endpoint] / self.total_blocks[endpoint]

    def estimate_sync_time(self, endpoint: str, window_s: int = 30) -> Union[str, float]:
        """
        Estimate ETA based on a windowed trend:
        - collect points in last `window_s` seconds
        - compute rate = (lag_start - lag_end) / dt
        - ETA = lag_end / rate

        If lag isn't decreasing, returns a message instead of a number.
        """
        with self._lock:
            hist = list(self.lag_history.get(endpoint, []))

        if len(hist) < 3:
            return "Not enough data"

        now = time.time()
        window = [(t, lag) for (t, lag, _bn) in hist if now - t <= window_s]
        if len(window) < 3:
            return "Not enough data"

        t0, lag0 = window[0]
        t1, lag1 = window[-1]
        dt = t1 - t0
        if dt <= 0:
            return "Not enough data"

        dlag = lag0 - lag1  # positive => lag decreasing
        if dlag <= 0:
            return "Block lag not decreasing"

        rate = dlag / dt
        if rate <= 0:
            return "Block lag not decreasing"

        return lag1 / rate


# ───────── worker thread ─────────
def poll_latest_block(w3: Web3, name: str, rate: float, stop_at: float, monitor: LatencyMonitor) -> None:
    """
    Poll latest block until stop_at.
    Each iteration:
      - request latest block
      - measure request latency
      - compute block lag (now - block.timestamp)
      - record metrics into monitor
    """
    while time.time() < stop_at:
        try:
            t0 = time.time()
            block = w3.eth.get_block("latest", False)
            t1 = time.time()

            elapsed = t1 - t0
            lag = int(t1) - int(block["timestamp"])
            bn = int(block["number"])

            monitor.update(name, sample_ts=t1, elapsed=elapsed,
                           lag_seconds=lag, block_number=bn)

            LOG.debug("[%s] block=%s latency=%.2fms lag=%s", name,
                      bn, elapsed * 1000.0, seconds_to_human_readable(lag))
        except Exception as e:
            LOG.warning("[%s] RPC polling failed: %s", name, str(e))

        time.sleep(rate)


def get_client_version(w3: Web3) -> str:
    # web3 v5: clientVersion, web3 v6+: client_version
    try:
        return w3.clientVersion  # type: ignore[attr-defined]
    except Exception:
        try:
            return w3.client_version  # type: ignore[attr-defined]
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
    Professional stance:
    - Only trust eth_chainId for the Chain ID.
    - If blocked/unavailable, return None (do not guess with net_version).
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
    Network ID (net_version) is *not* guaranteed equal to chainId.
    Only used when --show-netid for diagnostics.
    """
    try:
        net = getattr(w3, "net", None)
        if net is not None and hasattr(net, "version"):
            v = net.version  # type: ignore[attr-defined]
            if isinstance(v, str) and v.isdigit():
                return int(v)
    except Exception:
        pass

    resp = _rpc_make_request(w3, "net_version", [])
    if resp:
        val = resp.get("result")
        if isinstance(val, str) and val.isdigit():
            return int(val)
    return None


# ─────────── main runner ───────────
def run(
    endpoints: Dict[str, str],
    duration: int,
    rate: float,
    eta_window: int,
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
    stop_at = time.time() + duration
    monitor = LatencyMonitor()
    threads: List[threading.Thread] = []
    failed_endpoints: Dict[str, str] = {}

    # Load ChainList chainId->name map once per run (cached + TTL)
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

    # Start one polling thread per endpoint
    for name, url in endpoints.items():
        try:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 10}))

            # Some chains (Polygon/BNB/etc) need PoA middleware; safe to inject when available.
            if geth_poa_middleware is not None:
                try:
                    # type: ignore[arg-type]
                    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                except Exception:
                    pass

            # Quick connectivity test
            _ = w3.eth.block_number

            # Metadata (chainId may be blocked by some gateways; that's OK)
            chain_id = get_chain_id(w3)
            net_id = get_network_id(w3) if show_netid else None

            monitor.set_client_version(name, get_client_version(w3))
            monitor.set_chain(name, chain_id, net_id)

            t = threading.Thread(target=poll_latest_block, args=(
                w3, name, rate, stop_at, monitor), daemon=True)
            t.start()
            threads.append(t)

        except Exception as e:
            LOG.warning("[%s] Skipping due to connection issue: %s", name, e)
            failed_endpoints[name] = str(e)

    for t in threads:
        t.join()

    # ───── summary table ─────
    LOG.info("Average metrics after the test completes:")

    hdr = (
        f"{'Endpoint':<46}"
        f"{'AvgLatency (ms)':>15} "
        f"{'AvgBlockLag':>15} "
        f"{'ETA':>15} "
        f"{'Block':>12} "
        f"{'Chain':>26} "
        f"{'ChainId':>16} "
    )
    if show_netid:
        hdr += f"{'NetId':>8} "
    hdr += "Client Version"

    LOG.info(hdr)
    LOG.info("=" * len(hdr))

    for name in endpoints:
        if name in failed_endpoints:
            row = (
                f"[{name:<43}] {'N/A':>15} {'N/A':>15} {'Conn Failed':>15} "
                f"{'N/A':>12} {'N/A':>26} {'N/A':>16} "
            )
            if show_netid:
                row += f"{'N/A':>8} "
            row += "N/A"
            LOG.info(row)
            continue

        lat = monitor.avg_latency_ms(name)
        lag_s = monitor.avg_block_lag_seconds(name)
        lag_str = seconds_to_human_readable(lag_s)

        eta = monitor.estimate_sync_time(name, window_s=eta_window)
        eta_str = seconds_to_human_readable(
            eta) if isinstance(eta, (int, float)) else eta

        bn = monitor.last_block_numbers.get(name, 0)
        chain_id = monitor.chain_ids.get(name)
        chain_id_str = f"{chain_id} / {hex(chain_id)}" if isinstance(
            chain_id, int) else "N/A"

        chain_name = monitor.chain_names.get(name, "Unknown")
        ver = monitor.client_versions.get(name, "N/A")

        row = (
            f"[{name:<43}] {lat:>15.2f} {lag_str:>15} {eta_str:>15} "
            f"{bn:>12,} {chain_name:>26} {chain_id_str:>16} "
        )

        if show_netid:
            net_id = monitor.network_ids.get(name)
            net_id_str = str(net_id) if isinstance(net_id, int) else "N/A"
            row += f"{net_id_str:>8} "

        row += ver
        LOG.info(row)


# ─────────── argparse & config ───────────
def load_endpoints(group: str, config_path: pathlib.Path) -> Dict[str, str]:
    try:
        data = json.loads(config_path.read_text())
    except FileNotFoundError as exc:
        raise SystemExit(f"Config file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {config_path}: {exc}") from exc

    if group not in data:
        raise SystemExit(f"No group '{group}' in {config_path}")

    group_data = data[group]
    if not isinstance(group_data, dict):
        raise SystemExit(
            f"Group '{group}' must be an object/dict of name->url in {config_path}")

    out: Dict[str, str] = {}
    for k, v in group_data.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k] = v
    return out


def cli() -> None:
    default_cfg = pathlib.Path(__file__).with_name("endpoints.json")

    p = argparse.ArgumentParser(
        description="Monitor block-lag & latency for a group of RPC endpoints.")
    p.add_argument("group", help="Group name in endpoints.json, e.g. chi-op")
    p.add_argument("--duration", "-d", type=int, default=30,
                   help="Test length in seconds (default: 30)")
    p.add_argument("--rate", "-r", type=float, default=0.09,
                   help="Delay between RPC calls in seconds (default: 0.09)")
    p.add_argument(
        "--eta-window",
        type=int,
        default=30,
        help="Seconds of history used to estimate ETA (default: 30). Increase for bursty stage sync.",
    )
    p.add_argument(
        "--config",
        "-c",
        type=pathlib.Path,
        default=default_cfg,
        help=f"Path to endpoints.json (default: {default_cfg})",
    )

    # Output/diagnostics
    p.add_argument(
        "--show-netid",
        action="store_true",
        help="Show net_version (Network ID) column for diagnostics. Not guaranteed to equal chainId.",
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
        eta_window=args.eta_window,
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
