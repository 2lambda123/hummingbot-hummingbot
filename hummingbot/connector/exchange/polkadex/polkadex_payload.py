def create_asset(asset):
    if asset == "polkadex":
        return {"polkadex": None}
    else:
        return {"asset": asset}


def cancel_order(runtime_config, order_id):
    cancel_req = {
        "id": str(order_id)
    }
    return runtime_config.create_scale_object("CancelOrderPayload").encode(cancel_req)


def create_order(runtime_config, price, qty, order_type, side, proxy, base, quote, nonce):
    order = {
        "user": proxy,
        "pair": {
            "base_asset": create_asset(base),
            "quote_asset": create_asset(quote)
        },
        "qty": qty,
        "price": price,
        "nonce": nonce
    }
    if order_type == "LIMIT":
        order["order_type"] = {"LIMIT": None}
    else:
        order["order_type"] = {"MARKET": None}

    if side == "Bid":
        order["side"] = {"Bid": None}
    else:
        order["side"] = {"Ask": None}

    print(order)
    return runtime_config.create_scale_object("OrderPayload").encode(order)
