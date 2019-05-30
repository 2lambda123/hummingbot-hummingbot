#!/usr/bin/env python

from os.path import join, realpath
import sys; sys.path.insert(0, realpath(join(__file__, "../../")))

from nose.plugins.attrib import attr

import asyncio
import logging
import unittest
import conf
from typing import (
    Optional
)
from hummingbot.market.coinbase_pro.coinbase_pro_market import CoinbaseProAuth
from hummingbot.market.coinbase_pro.coinbase_pro_user_stream_tracker import CoinbaseProUserStreamTracker


@attr('unstable')
class CoinbaseProUserStreamTrackerUnitTest(unittest.TestCase):
    user_stream_tracker: Optional[CoinbaseProUserStreamTracker] = None

    @classmethod
    def setUpClass(cls):
        cls.ev_loop: asyncio.BaseEventLoop = asyncio.get_event_loop()
        cls.coinbase_pro_auth = CoinbaseProAuth(conf.coinbase_pro_api_key,
                                                conf.coinbase_pro_secret_key,
                                                conf.coinbase_pro_passphrase)
        cls.symbols = ["ETH-USDC"]
        cls.user_stream_tracker: CoinbaseProUserStreamTracker = CoinbaseProUserStreamTracker(
            coinbase_pro_auth=cls.coinbase_pro_auth, symbols=cls.symbols)
        cls.user_stream_tracker_task: asyncio.Task = asyncio.ensure_future(cls.user_stream_tracker.start())

    def test_user_stream(self):
            # Wait process some msgs.
            self.ev_loop.run_until_complete(asyncio.sleep(120.0))
            print(self.user_stream_tracker.user_stream)


def main():
    logging.basicConfig(level=logging.INFO)
    unittest.main()


if __name__ == "__main__":
    main()
