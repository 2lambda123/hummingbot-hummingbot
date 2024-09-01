<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from hummingbot.connector.exchange.chainflip_lp import chainflip_lp_constants as CONSTANTS
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.logger import HummingbotLogger
=======
=======
from decimal import Decimal
>>>>>>> 52298288f (fix: make it actually connect to chainflip, and fetch balance)
from typing import Any, Dict, List

from hummingbot.connector.exchange.chainflip_lp import chainflip_lp_constants as CONSTANTS
from hummingbot.connector.utils import combine_to_hb_trading_pair
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
=======
import logging
from typing import Any, Dict, List, Optional

from hummingbot.connector.exchange.chainflip_lp import chainflip_lp_constants as CONSTANTS
from hummingbot.connector.utils import combine_to_hb_trading_pair
from hummingbot.logger import HummingbotLogger
>>>>>>> 622c18947 ((fix) fix tests and make chainflip lp codebase updates)


class DataFormatter:
    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(HummingbotLogger.logger_name_for_class(cls))

        return cls._logger

    @classmethod
    def hex_str_to_int(cls, data: str):
        return int(data, 16)

    @classmethod
<<<<<<< HEAD
<<<<<<< HEAD
    def format_hex_balance(cls, balance: str, asset: Dict[str, str]):
<<<<<<< HEAD
<<<<<<< HEAD
        cls.logger().info(f"Converting {balance} as {asset}")

=======
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
        int_balance = cls.hex_str_to_int(balance)
        cls.logger().info(f"Balance for {balance} as {int_balance}")

        precision = cls.format_asset_precision(asset)
<<<<<<< HEAD
        cls.logger().info(f"Precision for {balance} is {precision}")

        value = int_balance / precision
        cls.logger().info(f"Converted value is {value}")

        return value
=======
        return int_balance / precision
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
=======
    def format_hex_balance(cls, logger, balance: str, asset: Dict[str, str]):
        logger.info("Converting " + str(balance) + " as " + str(asset))
=======
    def format_hex_balance(cls, balance: str, asset: Dict[str, str]):
<<<<<<< HEAD
        cls.logger().info(f"Converting {balance} as {asset}")
>>>>>>> 622c18947 ((fix) fix tests and make chainflip lp codebase updates)
=======
        cls.logger().debug(f"Converting {balance} as {asset}")
>>>>>>> ffb9c2b3c ((fix) fix test failures and errors)

=======
>>>>>>> af09807ef ((refactor) remove unneccessary logs and make minor fixes)
        int_balance = cls.hex_str_to_int(balance)
        precision = cls.format_asset_precision(asset)
        value = int_balance / precision
<<<<<<< HEAD
        cls.logger().debug(f"Converted value is {value}")

<<<<<<< HEAD
        return Decimal(value)
>>>>>>> 52298288f (fix: make it actually connect to chainflip, and fetch balance)
=======
=======
>>>>>>> af09807ef ((refactor) remove unneccessary logs and make minor fixes)
        return value
>>>>>>> 622c18947 ((fix) fix tests and make chainflip lp codebase updates)

    @classmethod
    def format_amount(cls, amount: float | int, asset: Dict[str, str]):
        precision = cls.format_asset_precision(asset)
        long_amount = amount * precision
        return cls.int_to_hex_str(int(long_amount))

    @classmethod
    def format_price(cls, price: int | str, base_asset: Dict[str, str], quote_asset: Dict[str, str], sqrt_price=True):
        """
        for example: to get the price of the ETH/USDC pair from the sqrt_price
        where the provided price is 4512835869581138250956800
        We Calculate:
        current_price = 4512835869581138250956800 / 2**96
        current_price = current_price ** 2 (provided the price is a square-root price)
        formated_price = (current_price * base_asset_precision)/quote_asset_precision
        """
        base_precision = cls.format_asset_precision(base_asset)
        quote_precision = cls.format_asset_precision(quote_asset)
<<<<<<< HEAD
<<<<<<< HEAD
        if isinstance(price, str):
            price = cls.hex_str_to_int(price)
        if sqrt_price:
            current_price = price / (2**CONSTANTS.SQRT_PRICE_FRACTIONAL_BITS)
            current_price = current_price**2
        else:
            current_price = price / (2**CONSTANTS.FRACTIONAL_BITS)

        formated_price = (current_price * base_precision) / quote_precision
=======
        
=======
        if isinstance(price, str):
            price = cls.hex_str_to_int(price)
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
        if sqrt_price:
            current_price = price / (2**CONSTANTS.SQRT_PRICE_FRACTIONAL_BITS)
            current_price = current_price**2
        else:
            current_price = price / (2**CONSTANTS.FRACTIONAL_BITS)

<<<<<<< HEAD
        formated_price = (current_price * base_precision)/quote_precision
>>>>>>> 730e68a15 ((refactor) update code and implement review changes)
=======
        formated_price = (current_price * base_precision) / quote_precision
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
        return formated_price

    @classmethod
    def int_to_hex_str(cls, data: int):
        return str(hex(data))

    @classmethod
    def format_order_response(cls, response, base_asset, quote_asset):
        data = response["result"]
        limit_orders = data["limit_orders"]
        asks = []
        bids = []
        for order in limit_orders["asks"]:
            tick = order["tick"]
            price = cls.convert_tick_to_price(tick, base_asset, quote_asset)
<<<<<<< HEAD
<<<<<<< HEAD
=======

>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
=======
>>>>>>> 622c18947 ((fix) fix tests and make chainflip lp codebase updates)
            asks.append({"price": price, "tick": tick})
        for order in limit_orders["bids"]:
            tick = order["tick"]
            price = cls.convert_tick_to_price(tick, base_asset, quote_asset)
            bids.append({"price": price, "tick": tick})
        return {"asks": asks, "bids": bids}

    @classmethod
    def format_balance_response(cls, response, chain_config: dict = CONSTANTS.DEFAULT_CHAIN_CONFIG):
        data = response["result"]
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
        cls.logger().info(f"Mapping {data} as balance")
=======
        logger.info("Mapping " + str(data) + " as balance")
>>>>>>> 52298288f (fix: make it actually connect to chainflip, and fetch balance)
=======
        cls.logger().info(f"Mapping {data} as balance")
>>>>>>> 622c18947 ((fix) fix tests and make chainflip lp codebase updates)
=======
>>>>>>> af09807ef ((refactor) remove unneccessary logs and make minor fixes)

        chains = data.keys()

        balance_map = {}
<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 52298288f (fix: make it actually connect to chainflip, and fetch balance)
        for chain in chains:
            assets = data[chain].keys()
            for asset in assets:
<<<<<<< HEAD
<<<<<<< HEAD
<<<<<<< HEAD
                token = f"{asset}-{chain}"
                balance_map[token] = cls.format_hex_balance(data[chain][asset], {"chain": chain, "asset": asset})
<<<<<<< HEAD
=======
        for key in keys:
            for asset in data[key]:
<<<<<<< HEAD
                balance_map[asset["asset"]] = cls.format_hex_balance(asset["balance"], {"chain": key, "asset": asset})
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
=======
                balance_map[asset["asset"]] = cls.format_hex_balance(
                    asset["balance"], {"chain": key, "asset": asset["asset"]}
                )
>>>>>>> cb0a3d276 ((refactor) implement review changes)
=======
                token = str(asset) + "/" + str(chain)
                logger.info("Mapping " + token)
=======
                if asset in chain_config:
                    if chain_config[asset] != chain:
                        continue  # skip asset balance
                token = f"{asset}"
                balance_map[token] = Decimal(cls.format_hex_balance(data[chain][asset], {"chain": chain, "asset": asset}))
>>>>>>> 2df344816 ((refactor) add order update and fix balance mapping)

                balance_map[token] = cls.format_hex_balance(
                    logger,
                    data[chain][asset],
                    {"chain": chain, "asset": asset}
                )

>>>>>>> 52298288f (fix: make it actually connect to chainflip, and fetch balance)
=======
                token = f"{asset}-{chain}"
                cls.logger().info("Mapping " + token)

                balance_map[token] = cls.format_hex_balance(data[chain][asset], {"chain": chain, "asset": asset})
>>>>>>> 622c18947 ((fix) fix tests and make chainflip lp codebase updates)
=======

>>>>>>> af09807ef ((refactor) remove unneccessary logs and make minor fixes)
        return balance_map

    @classmethod
    def format_all_market_response(cls, response):
        """
        return as a list of dict containing just base asset dict and quote asset dict
        """
        data: Dict = response["result"]["fees"]
        keys: List = data.keys()
        format_list = []
        for key in keys:
            chain = key
            for symbol in data[key]:
                try:

                    base_asset = {"chain": chain, "asset": symbol}
                    quote_asset = data[key][symbol]["quote_asset"]
                    trading_symbol = cls.format_assets_to_market_symbol(base_asset, quote_asset)
                    format_list.append({"symbol": trading_symbol, "base_asset": base_asset, "quote_asset": quote_asset})
                except Exception:
                    continue
        return format_list

    @classmethod
    def format_all_assets_response(cls, response: Dict, chain_config=CONSTANTS.DEFAULT_CHAIN_CONFIG):
        def filter_method(value):
            if value["asset"] in chain_config:
                if value["chain"] != chain_config[value["asset"]]:  # :)
                    return False
            return True

        result = response["result"]
        formatted_asset_list = list(filter(filter_method, result))
        return formatted_asset_list

    @classmethod
    def format_error_response(cls, response: Dict):
        # figure a better way to handle errors
        return None

    @classmethod
    def format_asset_precision(cls, asset: Dict[str, str]):
<<<<<<< HEAD
<<<<<<< HEAD
        return CONSTANTS.ASSET_PRECISIONS[asset["chain"]][asset["asset"]]
=======
        precisions = CONSTANTS.ASSET_PRECISIONS
        if asset["chain"] in precisions.keys():
            chain_precisions = precisions[asset["chain"]]
            asset_precision = chain_precisions.get(asset["asset"], chain_precisions["Default"])
        else:
            asset_precision = precisions["Ethereum"]["Default"]
        return asset_precision
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
=======
        return CONSTANTS.ASSET_PRECISIONS[asset["chain"]][asset["asset"]]
>>>>>>> 52298288f (fix: make it actually connect to chainflip, and fetch balance)

    @classmethod
    def format_orderbook_response(cls, response: Dict, base_asset: Dict[str, str], quote_asset: Dict[str, str]):
        data = response["result"]
        bids = list(
            map(
                lambda x: {
                    "amount": cls.format_hex_balance(x["amount"], base_asset),
                    "price": cls.format_price(
                        x["sqrt_price"],
                        base_asset,
                        quote_asset,
                    ),
                },
                data["bids"],
            )
        )
        asks = list(
            map(
                lambda x: {
                    "amount": cls.format_hex_balance(x["amount"], quote_asset),
                    "price": cls.format_price(
                        x["sqrt_price"],
                        base_asset,
                        quote_asset,
                    ),
                },
                data["asks"],
            )
        )
        format_data = {"bids": bids, "asks": asks, "id": response.get("id", 1)}
        return format_data

    @classmethod
    def format_supported_assets(cls, all_pairs: List[Dict[str, str]]):
        """
        format the trading pair list of dict to a list of string in
        the format of {base_asset}-{quote-asset}
        """
        pairs = []
        for pair in all_pairs:
            pairs.append(cls.format_assets_to_market_symbol(pair["base_asset"], pair["quote_asset"]))
        return pairs

    @classmethod
    def format_trading_pair(cls, pair: str, all_assets: List[Dict[str, str]]):
        """
        format a trading pair from {base_asset}-{quote_asset}
        to the format needed for lp rpc calls
        e.g ETH-USDT =>
        {
            "base_asset":{"chain":"Ethereum","asset":"ETH"},
            "quote_asset":{"chain":"Ethereum","asset":"USDT"},
        }
        """
        data = {}
        base_asset, quote_asset = pair.split("-")
        base_asset_list = list(filter(lambda x: x["asset"].upper() == base_asset.upper(), all_assets))
        quote_asset_list = list(filter(lambda x: x["asset"].upper() == quote_asset.upper(), all_assets))
        data["base_asset"] = base_asset_list[0] if base_asset_list else None
        data["quote_asset"] = quote_asset_list[0] if quote_asset_list else None

        return data

    @classmethod
    def format_symbol_list(cls, all_assets: List[Dict[str, str]]):
        """
        returns a list of just the symbols e.g ["ETH","USDT","BTC"]
        """
        return list(set(map(lambda x: x["asset"], all_assets)))
<<<<<<< HEAD
<<<<<<< HEAD

=======
>>>>>>> 9979ea9b9 ((refactor) update code and tests)
=======

>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
    @classmethod
    def format_market_pairs(cls, all_market: List[Dict[str, Dict]]):
        """
        Convert our symbol to HB Symbol
        """
        format_list = []
        for market in all_market:
            base_asset = market["base_asset"]["asset"]
            quote_asset = market["quote_asset"]["asset"]
            format_list.append(combine_to_hb_trading_pair(base_asset, quote_asset))
        return format_list

    @classmethod
    def format_market_price(cls, response: Dict[str, Any]):
        """
        return the float formatted price
        """
        data = response["result"]
        base_asset = data["base_asset"]
        quote_asset = data["quote_asset"]
        sell_price = cls.hex_str_to_int(data["sell"])
        buy_price = cls.hex_str_to_int(data["buy"])
        formatted_buy_price = cls.format_price(buy_price, base_asset, quote_asset)
        formatted_sell_price = cls.format_price(sell_price, base_asset, quote_asset)
        normal_price = (formatted_buy_price + formatted_sell_price) / 2
        formatted_data = {"buy": formatted_buy_price, "sell": formatted_sell_price, "price": normal_price}
        return formatted_data

    @classmethod
<<<<<<< HEAD
<<<<<<< HEAD
    def format_assets_to_market_symbol(cls, base_asset: Dict[str, str] | str, quote_asset: Dict[str, str] | str):
        if isinstance(base_asset, str):
            base = base_asset
        else:
            base = base_asset["asset"]
        if isinstance(quote_asset, str):
            quote = quote_asset
        else:
            quote = quote_asset["asset"]
        return f"{base}-{quote}"

    @classmethod
    def format_order_fills_response(cls, response: Dict, address: str, all_assets: List[Dict[str, str]]):
        def format_single_order_fill(order):
            trading_pair = cls.format_assets_to_market_symbol(order["base_asset"], order["quote_asset"])
            asset = cls.format_trading_pair(trading_pair, all_assets)
            data = {
                "trading_pair": trading_pair,
                "side": order["side"],
                "id": order["id"],
                "base_amount": cls.format_hex_balance(order["bought"], asset["base_asset"]),
                "quote_amount": cls.format_hex_balance(order["sold"], asset["quote_asset"]),
<<<<<<< HEAD
                "price": cls.convert_tick_to_price(order["tick"], asset["base_asset"], asset["quote_asset"]),
            }
            return data
=======
    def format_assets_to_market_symbol(
        cls, 
        base_asset:Dict[str, str] | str, 
        quote_asset:Dict[str, str] | str
    ):
        if type(base_asset) == str:
=======
    def format_assets_to_market_symbol(cls, base_asset: Dict[str, str] | str, quote_asset: Dict[str, str] | str):
        if isinstance(base_asset, str):
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
            base = base_asset
        else:
            base = base_asset["asset"]
        if isinstance(quote_asset, str):
            quote = quote_asset
        else:
            quote = quote_asset["asset"]
        return f"{base}-{quote}"

    @classmethod
    def format_order_fills_response(cls, response: Dict, address: str, all_assets: List[Dict[str, str]]):
        def format_single_order_fill(order):
            trading_pair = cls.format_assets_to_market_symbol(order["base_asset"], order["quote_asset"])
            asset = cls.format_trading_pair(trading_pair, all_assets)
            data = {
                "trading_pair": trading_pair,
                "side": order["side"],
                "id": order["id"],
                "base_amount": cls.format_hex_balance(order["bought"], asset["base_asset"]),
                "quote_amount": cls.format_hex_balance(order["sell"], asset["quote_asset"]),
=======
>>>>>>> 622c18947 ((fix) fix tests and make chainflip lp codebase updates)
                "price": cls.convert_tick_to_price(order["tick"], asset["base_asset"], asset["quote_asset"]),
            }
            return data

<<<<<<< HEAD
>>>>>>> 63271bb03 ((refactor) update and cleanup chainflip connector codes)

        data = response["result"]
        fills: Dict = data["fills"]
        if len(fills) == 0:
            return []
        # filter the fills to return only limit orders
        limit_orders_fills = list(filter(lambda x: x[0] == "limit_orders", fills.items()))
=======
        data = response["result"]
        fills: Dict = data["fills"]
        # filter the fills to return only limit orders
<<<<<<< HEAD
        limit_orders_fills = list(filter(lambda x: x[0] == "limit_order", fills.items()))
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
=======
        limit_orders_fills = list(filter(lambda x: x[0] == "limit_orders", fills.items()))
>>>>>>> 622c18947 ((fix) fix tests and make chainflip lp codebase updates)
        if not limit_orders_fills:
            return []
        # filter the limit orders fill by the user address
<<<<<<< HEAD
<<<<<<< HEAD
        user_orders = list(filter(lambda x: x[1]["lp"] == address, limit_orders_fills))
        if not user_orders:
            return []
        main_data = list(map(lambda x: x[1], user_orders))
=======
        user_orders = list(filter(
            lambda x: x[1]["lp"] == address,
            limit_orders_fills
        ))
        if not user_orders:
            return []
        #get the values of the 
        main_data =  list(map(
            lambda x: x[1],
            user_orders
        ))
>>>>>>> 63271bb03 ((refactor) update and cleanup chainflip connector codes)
=======
        user_orders = list(filter(lambda x: x[1]["lp"] == address, limit_orders_fills))
        if not user_orders:
            cls.logger().info("No order fill found for current address")
            return []
        # get the values of the
        main_data = list(map(lambda x: x[1], user_orders))
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
        formatted_data = list(map(format_single_order_fill, main_data))
        return formatted_data

<<<<<<< HEAD
=======
    @classmethod
    def format_place_order_response(cls, response: Dict):
        """
        return data - order_id, tick
        """
        data = response["result"]
        main_response = data["tx_details"]["response"][-1]  # get the last elements in the order response
        return_data = {"order_id": main_response["id"], "tick": main_response["tick"]}
        return return_data

>>>>>>> 9979ea9b9 ((refactor) update code and tests)
    @classmethod
<<<<<<< HEAD
    def format_place_order_response(cls, response: Dict):
        """
        return data - order_id, tick
        """
        data = response["result"]
        main_response = data["tx_details"]["response"][-1]  # get the last elements in the order response
        return_data = {"order_id": main_response["id"], "tick": main_response["tick"]}
        return return_data

    @classmethod
=======
>>>>>>> 67f0d8422 ((fix) fix code errors, format errors and test errors)
    def convert_tick_to_price(cls, tick: int, base_asset: Dict[str, str], quote_asset: Dict[str, str]):
        base_precision = cls.format_asset_precision(base_asset)
        quote_precision = cls.format_asset_precision(quote_asset)
        raw_price = 1.0001**tick
        price = (raw_price * base_precision) / quote_precision
        return price

    @classmethod
    def convert_bot_id_to_int(cls, id: str):
        """
        The reason for this method is because chainflip only accepts numeric id
        and hummingbot generates a string id.
        so we will be converting the string to integer.
        in the exchange file, the string id has already been
        converted to a hex format in the buy and sell
        method which will make it easier to be converting to integerr
        """
        # convert the hex str to integer.
        integer = cls.hex_str_to_int(id)
        # convert the integer to string reduce the length
        # the length might be too much to pass as an id
        string_int = str(integer)[:10]
        new_id = int(string_int)
        return new_id

    @classmethod
    def format_order_status(cls, response: dict, id: str, side: str):
        result = response["result"]
        limit_orders = result["limit_orders"]
        if side == CONSTANTS.SIDE_SELL:
            data = limit_orders["asks"]
        else:
            data = limit_orders["bids"]
        if len(data) == 0:
            return None  # no more open orders
        order = list(filter(
            lambda x: x["id"] == id,
            data
        ))
        if len(order) == 0:
            return None
        else:
            return order[0]
