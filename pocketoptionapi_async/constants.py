"""
Constants and configuration for the PocketOption API
"""

from typing import Dict, List, Optional
import random

# Asset mappings with their corresponding IDs (MASTER 2026 REGISTRY)
ASSETS: Dict[str, int] = {
    # Major Forex Pairs
    "EURUSD": 1, "GBPUSD": 56, "USDJPY": 63, "USDCHF": 62, "USDCAD": 61, "AUDUSD": 40, "NZDUSD": 90,
    "EURCAD": 10, "GBPCAD": 83, 
    "CADJPY": 11,  # <--- INJECTED

    # OTC Forex Pairs
    "EURUSD_otc": 66, "GBPUSD_otc": 86, "USDJPY_otc": 93, "USDCHF_otc": 92, "USDCAD_otc": 91,
    "AUDUSD_otc": 71, "AUDNZD_otc": 70, "AUDCAD_otc": 67, "AUDCHF_otc": 68, "AUDJPY_otc": 69,
    "CADCHF_otc": 72, "CADJPY_otc": 73, "CHFJPY_otc": 74, "EURCHF_otc": 77, "EURGBP_otc": 78,
    "EURJPY_otc": 79, "EURNZD_otc": 80, "GBPAUD_otc": 81, "GBPJPY_otc": 84, "NZDJPY_otc": 89,
    "NZDUSD_otc": 90,
    "EURCAD_otc": 166, "GBPCAD_otc": 168, "GBPAUD_otc": 160, "AUDCHF_otc": 161,
    "EURAUD_otc": 162,  # <--- INJECTED
    "GBPNZD_otc": 163,  # <--- INJECTED
    "LBPUSD_otc": 202,  # <--- INJECTED

    # --- REGIONAL OTC EXOTICS ---
    "KESUSD_otc": 173, "NGNUSD_otc": 172, "ZARUSD_otc": 171, "UAHUSD_otc": 170, "USDVND_otc": 174,
    "USDARS_otc": 175, "USDBDT_otc": 176, "USDBRL_otc": 177, "USDCOP_otc": 178, "USDMXN_otc": 179,
    "USDPKR_otc": 180, "USDPHP_otc": 181, "USDIDR_otc": 182, "USDMYR_otc": 183, "USDTHB_otc": 184,
    "AEDCNY_otc": 185, "BHDCNY_otc": 186, "JODCNY_otc": 187, "OMRCNY_otc": 188, "QARCNY_otc": 189,
    "SARCNY_otc": 190, "MADUSD_otc": 191, "TNDUSD_otc": 192, "YERUSD_otc": 193, "EURTRY_otc": 194,
    "USDCLP_otc": 195, "USDCNH_otc": 196, "USDDZD_otc": 197, "USDEGP_otc": 198, "USDSGD_otc": 201,
    "USDINR_otc": 164,  # <--- INJECTED

    # --- CRYPTOCURRENCIES (Extended 2026) ---
    "BTCUSD": 197, "BTCUSD_otc": 197, "ETHUSD": 272, "ETHUSD_otc": 272,
    "XRPUSD": 273, "XRPUSD_otc": 273, "LTCUSD": 204, "LTCUSD_otc": 204,
    "TONUSD_otc": 501, "AVAXUSD_otc": 502, "DOGEUSD_otc": 503, "SOLUSD_otc": 504,
    "MATICUSD_otc": 505, "ADAUSD_otc": 506, "TRXUSD_otc": 507, "DOTUSD": 458,
    "DOTUSD_otc": 458, "LNKUSD": 464, "DASH_USD": 209, "CRYPTIDX_otc": 450,
    "LINKUSD_otc": 464,  # <--- INJECTED
    "BNBUSD_otc": 508,   # <--- INJECTED

    # Commodities
    "XAUUSD": 2, "XAUUSD_otc": 169, "XAGUSD": 65, "XAGUSD_otc": 167,
    "UKBrent": 50, "UKBrent_otc": 164, "USCrude": 64, "USCrude_otc": 165,
    "XNGUSD": 311, "XNGUSD_otc": 399, "XPTUSD": 312, "XPTUSD_otc": 400,

    # Stock Indices
    "SP500": 321, "SP500_otc": 408, "NASUSD": 323, "NASUSD_otc": 410,
    "DJI30": 322, "DJI30_otc": 409, "JPN225": 317, "JPN225_otc": 405,
    "D30EUR": 318, "D30EUR_otc": 406, "E50EUR": 319, "E50EUR_otc": 407,
    "F40EUR": 316, "F40EUR_otc": 404, "E35EUR": 314, "E35EUR_otc": 402,
    "100GBP": 315, "100GBP_otc": 403, "AUS200": 305, "AUS200_otc": 306,

    # US Stocks & Variations
    "#AAPL": 5, "#AAPL_otc": 170, "Apple_otc": 170,
    "#MSFT": 24, "#MSFT_otc": 176, "Microsoft_otc": 521,
    "#TSLA": 186, "#TSLA_otc": 196, "Tesla_otc": 523,
    "#NVDA": 417, "#NVDA_otc": 417, "NVIDIA_otc": 417,
    "#AMZN": 412, "#AMZN_otc": 412, "Amazon_otc": 412,
    "#GOOG": 418, "#GOOG_otc": 418, "Google_otc": 418,
    "#NFLX": 182, "#NFLX_otc": 429, "#META_otc": 187,
    "Boeing_otc": 524, "American_Express_otc": 525,

    # Additional
    "EURRUB_otc": 200, "USDRUB_otc": 199, "EURHUF_otc": 460, "CHFNOK_otc": 457,
}

# WebSocket regions with their URLs
class Regions:
    """WebSocket region endpoints"""

    _REGIONS = {
        "EUROPA": "wss://api-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "SEYCHELLES": "wss://api-sc.po.market/socket.io/?EIO=4&transport=websocket",
        "HONGKONG": "wss://api-hk.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER1": "wss://api-spb.po.market/socket.io/?EIO=4&transport=websocket",
        "FRANCE2": "wss://api-fr2.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES4": "wss://api-us4.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES3": "wss://api-us3.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES2": "wss://api-us2.po.market/socket.io/?EIO=4&transport=websocket",
        "DEMO": "wss://demo-api-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "DEMO_2": "wss://try-demo-eu.po.market/socket.io/?EIO=4&transport=websocket",
        "UNITED_STATES": "wss://api-us-north.po.market/socket.io/?EIO=4&transport=websocket",
        "RUSSIA": "wss://api-msk.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER2": "wss://api-l.po.market/socket.io/?EIO=4&transport=websocket",
        "INDIA": "wss://api-in.po.market/socket.io/?EIO=4&transport=websocket",
        "FRANCE": "wss://api-fr.po.market/socket.io/?EIO=4&transport=websocket",
        "FINLAND": "wss://api-fin.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER3": "wss://api-c.po.market/socket.io/?EIO=4&transport=websocket",
        "ASIA": "wss://api-asia.po.market/socket.io/?EIO=4&transport=websocket",
        "SERVER4": "wss://api-us-south.po.market/socket.io/?EIO=4&transport=websocket",
    }

    @classmethod
    def get_all(cls, randomize: bool = True) -> List[str]:
        """Get all region URLs"""
        urls = list(cls._REGIONS.values())
        if randomize:
            random.shuffle(urls)
        return urls

    @classmethod
    def get_all_regions(cls) -> Dict[str, str]:
        """Get all regions as a dictionary"""
        return cls._REGIONS.copy()

    @classmethod
    def get_region(cls, region_name: str) -> Optional[str]:
        """Get specific region URL"""
        return cls._REGIONS.get(region_name.upper())

    @classmethod
    def get_demo_regions(cls) -> List[str]:
        """Get demo region URLs"""
        return [url for name, url in cls._REGIONS.items() if "DEMO" in name]


# Global constants
REGIONS = Regions()

# Timeframes (in seconds) - UPDATED FOR FAST TRADING
TIMEFRAMES = {
    "5s": 5,
    "10s": 10,
    "15s": 15,
    "30s": 30,
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}

# Connection settings
CONNECTION_SETTINGS = {
    "ping_interval": 20,  # seconds
    "ping_timeout": 10,  # seconds
    "close_timeout": 10,  # seconds
    "max_reconnect_attempts": 5,
    "reconnect_delay": 5,  # seconds
    "message_timeout": 30,  # seconds
}

# API Limits - UPDATED FOR 2026 PERFORMANCE
API_LIMITS = {
    "min_order_amount": 1.0,
    "max_order_amount": 50000.0,
    "min_duration": 1,  # Lowered from 5 to support S3 trading
    "max_duration": 43200,  # 12 hours in seconds
    "max_concurrent_orders": 50,
    "rate_limit": 500,  # Increased for rapid strategy execution
}

# Trade Types
OPTION_TYPES = {
    "QUICK_TRADING": 100,
    "DIGITAL_TRADING": 0,
}

# Default headers
DEFAULT_HEADERS = {
    "Origin": "https://pocketoption.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
