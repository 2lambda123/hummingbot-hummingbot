# import asyncio
# from flask import Flask, request
# from hummingbot.client.config.global_config_map import global_config_map

# api = Flask(__name__)

# verification_token = global_config_map.get("slack_verification_token").value


# @api.route('/test', methods=['GET'])
# def test():
#     return 'Here'


# @api.route('/slack/start', methods=['POST'])
# def slack():
#     print(f'verification token {verification_token}')
#     if request.form['token'] == verification_token:
#         payload = {'text': 'Welcome! Strategy started'}
#         return jsonify(payload)


# def run_api():
#     api.run(port=5000)
