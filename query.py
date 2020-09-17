#!/usr/bin/python3
#-*- coding:utf8 -*-

from web3 import Web3
from solcx import compile_source, install_solc, get_solc_version, set_solc_version
from pathlib import Path
from time import time
from collections import defaultdict
from random import choice


REQUIRED_SOLC_VERSION = '0.5.16' # solc version required by the contract source and openzeppelin headers
PROVIDER_URLS = ['https://mainnet.infura.io/v3/11ed32ed8b7947498852e4195a4495b2'] # list of Eth RPC nodes
WDGLD_CONTRACT_ADDRESS = Web3.toChecksumAddress('0x123151402076fc819b7564510989e475c9cd93ca') # wDGLD contract address


wdgld_contract_interface = None

def compile_contract():
	global wdgld_contract_interface
	# install the right solc version
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


w3 = None

def connect_to_eth(provider_url):
	global w3
	# connect to node
	w3 = Web3(Web3.HTTPProvider(provider_url))
	
	expected_block_number = (time() - 1599746465 + 10834409 * 10) / 10 # approximate expected Ethereum block number
	if not 1.1 * expected_block_number >= w3.eth.blockNumber  >= 0.9 * expected_block_number:
		# bad ethereum node
		w3 = None


wdgld_contract = None
ISSUE_ADDRESS = '0x0000000000000000000000000000000000000000'
PEGOUT_ADDRESS = None
TOTAL_SUPPLY = 0

def get_contract():
	global wdgld_contract
	# request contract
	wdgld_contract = w3.eth.contract(address=WDGLD_CONTRACT_ADDRESS, abi=wdgld_contract_interface['abi'])
	assert wdgld_contract.functions.name().call() == 'wrapped-DGLD', "Sanity check failed: The requested contract name is not 'wrapped-DGLD'."
	
	global PEGOUT_ADDRESS, TOTAL_SUPPLY
	PEGOUT_ADDRESS = wdgld_contract.functions.pegoutAddress().call()
	TOTAL_SUPPLY = wdgld_contract.functions.totalSupply().call()


def reset_balances():
	global balances, balances_block
	balances_block = 10379499 # contract creation block number
	balances = defaultdict(lambda: 0)


def update_balances(blocks_at_once=300000):
	global balances, balances_block
	
	# get transfer list
	to_block = min(w3.eth.blockNumber, balances_block + blocks_at_once)
	transfers = wdgld_contract.events.Transfer.getLogs(fromBlock=balances_block, toBlock=to_block)
	balances_block = to_block
	
	# calculate balances from transfers
	for transfer in transfers:
		from_address = transfer['args']['from']
		to_address = transfer['args']['to']
		value = transfer['args']['value']
		#print(from_address, to_address, value)
		balances[from_address] -= value
		balances[to_address] += value
		
		assert TOTAL_SUPPLY >= -balances[ISSUE_ADDRESS], "Sanity check failed: Total coin supply doesn't match the value derived from transfer listing."


def synchronized():
	if not w3 or not w3.isConnected(): return False
	
	return True


def balances_list():
	for addr in sorted(balances.keys()):
		value = balances[addr]
		if value > 0:
			yield addr, value


def generate_mapping(map_A, map_B):
	if sum(map_A.values()) != sum(map_B.values()):
		raise ValueError
	
	map_R = defaultdict(list)
	
	map_A_keys = sorted(map_A.keys())
	map_B_keys = sorted(map_B.keys())
	vT = sum(map_A.values())
	
	m = n = 0
	vA = vB = 0
	while m < len(map_A_keys) or n < len(map_B_keys):
		if vA == 0:
			kA = map_A_keys[m]
			vA = map_A[kA]
			m += 1
		
		if vB == 0:
			kB = map_B_keys[n]
			vB = map_B[kB]
			n += 1
		
		v = min(vA, vB)
		map_R[kA].append({'dgld':kB, 'value':v})
		vA -= v
		vB -= v
	
	return map_R


def ethbridge_mapping_updater():
	try:
		while wdgld_contract_interface == None:
			try:
				print("compiling contract")
				compile_contract()
			except AssertionError as error:
				print("could not compile contract:", error)
				continue
		
		while True:
			try:
				w3 = None
				wdgld_contract == None
				
				while not w3 or not w3.isConnected() or wdgld_contract == None:
					provider_url = choice(PROVIDER_URLS)
					print("connecting to eth node")
					connect_to_eth(provider_url)
					
					print("getting contract")
					get_contract()
				
				print("resetting balances")
				reset_balances()
				
				while synchronized():
					print("update balances", w3.eth.blockNumber - balances_block)
					update_balances()
					
					if w3.eth.blockNumber <= balances_block + 6:
						print("balances up to date")
						print(list(balances_list()))
				
				print("lost synchronization")
			
			except AssertionError as error:
				print("error:", error)
				continue
	
	except KeyboardInterrupt:
		print()
	
	