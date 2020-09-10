#!/usr/bin/python3
#-*- coding:utf8 -*-

from web3 import Web3
from solcx import compile_source, install_solc, get_solc_version, set_solc_version
from pathlib import Path
from time import time
from collections import defaultdict


# install the right solc version
REQUIRED_SOLC_VERSION = '0.5.16' # solc version required by the contract source and openzeppelin headers
try:
	if str(get_solc_version()) != REQUIRED_SOLC_VERSION:
		set_solc_version(REQUIRED_SOLC_VERSION)
except SolcNotInstalled:
	install_solc(REQUIRED_SOLC_VERSION)
	set_solc_version(REQUIRED_SOLC_VERSION)
assert str(get_solc_version()) == REQUIRED_SOLC_VERSION, f"Wrong solc version: {str(get_solc_version())} instead of required {REQUIRED_SOLC_VERSION}."


# compile wDLGD contract
wdgld_compiled_sol = compile_source(Path('dgld-smart-contracts/contracts/wrapped-DGLD.sol').read_text(), import_remappings=['openzeppelin-solidity/=./dgld-smart-contracts/node_modules/openzeppelin-solidity/', '-'])
wdgld_contract_id, wdgld_contract_interface = wdgld_compiled_sol.popitem()


# connect to Infura
PROVIDER_URL = 'https://mainnet.infura.io/v3/11ed32ed8b7947498852e4195a4495b2'
w3 = Web3(Web3.HTTPProvider(PROVIDER_URL))
assert w3.isConnected(), "Not connected to Infura."

if __debug__:
	expected_block_number = (time() - 1599746465 + 10834409 * 10) / 10 # approximate expected Ethereum block number
assert 1.1 * expected_block_number >= w3.eth.blockNumber  >= 0.9 * expected_block_number, f"Sanity check failed: Ethereum block number ({w3.eth.blockNumber}) must be +-10% of the expected value {expected_block_number}, assuming 10s block creation time."


# request contract
WDGLD_CONTRACT_ADDRESS = Web3.toChecksumAddress('0x123151402076fc819b7564510989e475c9cd93ca')
wdgld_contract = w3.eth.contract(address=WDGLD_CONTRACT_ADDRESS, abi=wdgld_contract_interface['abi'])
assert wdgld_contract.functions.name().call() == 'wrapped-DGLD', "Sanity check failed: The requested contract name is not 'wrapped-DGLD'."

# balances
ISSUE_ADDRESS = '0x0000000000000000000000000000000000000000'
PEGOUT_ADDRESS = '0x00000000000000000000000000000000009ddEAd'
balances_block = 10379499 # contract creation block number
balances = defaultdict(lambda: 0)

def update_balances():
	global balances, balances_block
	
	# get transfer list
	current_block = w3.eth.blockNumber
	transfers = wdgld_contract.events.Transfer.getLogs(fromBlock=balances_block)
	balances_block = current_block
	
	if __debug__:
		total_supply = wdgld_contract.functions.totalSupply().call()
	
	# calculate balances from transfers
	for transfer in transfers:
		from_address = transfer['args']['from']
		to_address = transfer['args']['to']
		value = transfer['args']['value']
		#print(from_address, to_address, value)
		balances[from_address] -= value
		balances[to_address] += value
		
		assert total_supply >= -balances[ISSUE_ADDRESS], "Sanity check failed: Total coin supply doesn't match the value derived from transfer listing."


if __name__ == '__main__':
	update_balances()
	
	for addr, value in balances.items():
		if value > 0:
			print(addr, value)

