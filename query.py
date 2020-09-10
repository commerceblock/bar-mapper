#!/usr/bin/python3
#-*- coding:utf8 -*-

from web3 import Web3
from solc import compile_source, install_solc, get_solc_version_string
from pathlib import Path
import os


try:
	os.environ['SOLC_BINARY'] = str(Path.home() / '.py-solc/solc-v0.4.25/bin/solc')
	assert get_solc_version_string().startswith('Version: 0.4.25+')
except (AssertionError, FileNotFoundError):
	install_solc('v0.4.25')

assert get_solc_version_string().startswith('Version: 0.4.25+')


w3 = Web3(Web3.HTTPProvider('https://ropsten.infura.io/v3/11ed32ed8b7947498852e4195a4495b2'))

assert w3.isConnected()


print(w3.eth.blockNumber)


compiled_sol = compile_source(Path('dgld-smart-contracts/contracts/wrapped-DGLD.sol').read_text(), import_remappings=['=./dgld-smart-contracts/node_modules/', '-'])
contract_id, contract_interface = compiled_sol.popitem()

wdgld_contract_address = '0x123151402076fc819b7564510989e475c9cd93ca'

contract = w3.eth.contract(address=wdgld_contract_address, abi=contract_interface["abi"])

print(contract.functions.balanceOf('0xe0238da09cab56b3066f26f98657dcce801c16b9').call())

#address = deploy_contract(w3, contract_interface)
#print(f'Deployed {contract_id} to: {address}\n')






'''
from collections import defaultdict
from decimal import Decimal
import os

import requests


INFURA_KEY = '11ed32ed8b7947498852e4195a4495b2'


def get_rpc_response(method, params=[]):
    url = "https://mainnet.infura.io/{}".format(INFURA_KEY)
    params = params or []
    data = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=data)
    return response.json()


def get_contract_transfers(address, decimals=18, from_block=None):
    """Get logs of Transfer events of a contract"""
    from_block = from_block or "0x0"
    transfer_hash = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    params = [{"address": address, "fromBlock": from_block, "topics": [transfer_hash]}]
    logs = get_rpc_response("eth_getLogs", params)
    from pprint import pprint as pp
    pp(logs)
    logs = logs['result']
    decimals_factor = Decimal("10") ** Decimal("-{}".format(decimals))
    for log in logs:
        log["amount"] = Decimal(str(int(log["data"], 16))) * decimals_factor
        log["from"] = log["topics"][1][0:2] + log["topics"][1][26:]
        log["to"] = log["topics"][2][0:2] + log["topics"][2][26:]
    return logs


def get_balances(transfers):
    balances = defaultdict(Decimal)
    for t in transfers:
        balances[t["from"]] -= t["amount"]
        balances[t["to"]] += t["amount"]
    bottom_limit = Decimal("0.00000000001")
    balances = {k: balances[k] for k in balances if balances[k] > bottom_limit}
    return balances


def get_balances_list(transfers):
    balances = get_balances(transfers)
    balances = [{"address": a, "amount": b} for a, b in balances.items()]
    balances = sorted(balances, key=lambda b: -abs(b["amount"]))
    return balances


if __name__ == '__main__':
	address = '0xa74476443119A942dE498590Fe1f2454d7D4aC0d'
	transfers = get_contract_transfers(address)
	balances = get_balances(transfers)
	print(balances)

'''



