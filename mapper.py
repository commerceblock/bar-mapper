#!/usr/bin/python3
#-*- coding:utf-8 -*-


from flask import Flask, request, abort, make_response
from pathlib import Path
import json
from requests import get
from requests.exceptions import Timeout
from web3 import Web3
from solcx import compile_source, install_solc, get_solc_version, set_solc_version
from solcx.exceptions import SolcNotInstalled
from time import time, sleep
from collections import defaultdict
from random import choice
from decimal import Decimal


mime_json = [('Content-Type', 'application/json')]
mime_xhtml = [('Content-Type', 'application/xhtml+xml'), ('Cache-Control', 'only-if-cached, max-age=604800')]
mime_css = [('Content-Type', 'text/css;charset=utf-8'), ('Cache-Control', 'only-if-cached, max-age=604800')]
mime_python = [('Content-Type', 'application/python;charset=utf-8'), ('Cache-Control', 'only-if-cached, max-age=604800')]
mime_javascript = [('Content-Type', 'application/javascript;charset=utf-8'), ('Cache-Control', 'only-if-cached, max-age=604800')]


app = Flask('bar_mapper')

DEBUG_FLAG = False
WSGI_PORT = 5000
WSGI_IP = '127.0.0.1'
REQUIRED_SOLC_VERSION = '0.5.16' # solc version required by the contract source and openzeppelin headers
PROVIDER_URLS = ['https://mainnet.infura.io/v3/11ed32ed8b7947498852e4195a4495b2'] # list of Eth RPC nodes (may be more than 1)
WDGLD_CONTRACT_ADDRESS = Web3.toChecksumAddress('0x123151402076fc819b7564510989e475c9cd93ca') # wDGLD contract address
ETHBRIDGE_DGLD_ADDRESS = 'gDxdzHvfK2a9ARMQQASJqCQ9K47SNUeiot' # Ethbridge DGLD address
ASSET_MAP_URL = 'https://s3.eu-west-1.amazonaws.com/gtsa-mapping/map.json' # static asset->bar map URL
UTXOS_API_URL_TEMPLATE = 'https://explorer.dgld.ch/api/address/utxos/%s' # DGLD explorer URL template to get utxo list
REQUEST_TIMEOUT = 4 # default timeout (seconds) for all http requests

w3 = None
wdgld_contract_interface = None
wdgld_contract = None
wdgld_total_supply = None

utxos_cache = {}
UTXOS_CACHE_TIMEOUT = 600

ISSUE_ADDRESS = '0x0000000000000000000000000000000000000000'
PEGOUT_ADDRESS = None


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
	wdgld_compiled_sol = compile_source(Path('dgld-smart-contracts/contracts/wrapped-DGLD.sol').read_text())
	wdgld_contract_id, wdgld_contract_interface = wdgld_compiled_sol.popitem()


def connect_to_eth(provider_url):
	global w3
	# connect to node
	w3 = Web3(Web3.HTTPProvider(provider_url))
	
	expected_block_number = (time() - 1599746465 + 10834409 * 10) / 10 # approximate expected Ethereum block number
	if not 1.1 * expected_block_number >= w3.eth.blockNumber  >= 0.9 * expected_block_number:
		# bad ethereum node
		w3 = None


def get_contract():
	global wdgld_contract
	# request contract
	wdgld_contract = w3.eth.contract(address=WDGLD_CONTRACT_ADDRESS, abi=wdgld_contract_interface['abi'])
	
	#assert wdgld_contract.functions.name().call() == 'wrapped-DGLD', "Sanity check failed: The requested contract name is not 'wrapped-DGLD'."


def reset_balances():
	global balances, balances_block, wdgld_total_supply
	wdgld_total_supply = None
	balances_block = 10379499 # contract creation block number
	balances = defaultdict(lambda: 0)


def update_balances(blocks_at_once=300000):
	global balances, balances_block, wdgld_total_supply
	
	wdgld_total_supply = wdgld_contract.functions.totalSupply().call()
	
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
		
		assert wdgld_total_supply >= -balances[ISSUE_ADDRESS], "Sanity check failed: Total coin supply doesn't match the value derived from transfer listing."


def synchronized():
	return w3 and w3.isConnected()


def balances_list():
	for addr in sorted(balances.keys()):
		value = balances[addr]
		if value > 0:
			yield addr, value


def generate_mapping(map_A, map_B):
	sA = sum(Decimal(str(_v)) for _v in map_A.values())
	sB = sum(Decimal(str(_v)) for _v in map_B.values())
	
	map_R = defaultdict(list)
	
	map_A_keys = sorted(map_A.keys())
	map_B_keys = sorted(map_B.keys())
	vT = sum(map_A.values())
	
	m = n = 0
	vA = Decimal(0)
	vB = Decimal(0)
	while m < len(map_A_keys) or n < len(map_B_keys):
		if vA == 0:
			kA = map_A_keys[m]
			vA = Decimal(str(map_A[kA])) * sB
			m += 1
		
		if vB == 0:
			kB = map_B_keys[n]
			vB = Decimal(str(map_B[kB])) * sA
			n += 1
		
		v = min(vA, vB)
		map_R[kA].append((kB, float(v / sA)))
		vA -= v
		vB -= v
		
		assert vA >= 0 and vB >= 0
	
	return map_R
	

def is_dgld_address(dgld):
	return 26 <= len(dgld) <= 35 and (dgld[0] in 'Gg') and dgld.isalnum()


def is_eth_address(eth):
	return len(eth) == 42 and eth[:2] == '0x' and all(_ch in '0123456789abcdef' for _ch in eth[2:].lower())


def is_asset_id(asset):
	return len(asset) == 64 and all(_ch in '0123456789abcdef' for _ch in asset.lower())


def download_asset_map():
	asset_map_request = get(ASSET_MAP_URL, timeout=REQUEST_TIMEOUT)
	if asset_map_request.status_code != 200:
		raise InvalidResponse(asset_map_request.status_code)
	
	asset_map_result = asset_map_request.json()
	asset_map_new = {}
	for number, entry in asset_map_result['assets'].items():
		asset = entry['tokenid']
		ref = entry['ref']
		mass = entry['mass']
		asset_map_new[asset] = {'asset':asset, 'ref':ref, 'mass':mass}
	
	return asset_map_new



class InvalidResponse(Exception):
	def __init__(self, status_code):
		super().__init__("Bad status code in server response")
		self.status_code = status_code


def download_utxos(url):
	try:
		utxos, r_time = utxos_cache[url]
		if r_time + UTXOS_CACHE_TIMEOUT < time():
			del utxos_cache[url]
		else:
			return utxos
	except KeyError:
		pass
	
	utxos_response = get(url, timeout=REQUEST_TIMEOUT)
	if utxos_response.status_code != 200:
		raise InvalidResponse(utxos_response.status_code)
	utxos = utxos_response.json()
	
	utxos_cache[url] = utxos, time()
	
	return utxos



def download_locked_assets(dgld_address):
	url = UTXOS_API_URL_TEMPLATE % dgld_address
	utxos = download_utxos(url)
	
	assets = {}
	
	for utxo in utxos['addrTxs']:
		asset = utxo['asset']
		value = utxo['value']
		assets[asset] = value
	
	return assets


@app.route('/')
def root():
	return Path('index.html').read_bytes(), 200, mime_xhtml


@app.route('/style.css')
def style_css():
	return Path('style.css').read_bytes(), 200, mime_css


@app.route('/client.py')
def client_py():
	return Path('client.py').read_bytes(), 200, mime_python


@app.route('/brython.js')
def brython_js():
	return Path('brython.js').read_bytes(), 200, mime_javascript


@app.route('/brython_stdlib.js')
def brython_stdlib_js():
	return Path('brython_stdlib.js').read_bytes(), 200, mime_javascript


@app.route('/asset-bar/<asset>')
def asset_bar(asset):
	"asset->bar: Takes an asset id, returns bar ref and mass, as defined in the asset map."
	
	if not is_asset_id(asset):
		return json.dumps({'error':'not an asset id', 'value':asset}), 415, mime_json
	
	bar = asset_map[asset]
	ref = bar['ref']
	mass = bar['mass']
	return json.dumps({'asset':asset, 'ref':ref, 'mass':mass}), 200, mime_json


@app.route('/dgld-asset/<dgld>')
def dgld_asset(dgld):
	"dgld->asset: Takes a DGLD address, returns list of asset covered by that address, with their values."
	
	if not is_dgld_address(dgld):
		return json.dumps({'error':'not a dgld address', 'value':dgld}), 400, mime_json
	
	url = UTXOS_API_URL_TEMPLATE % dgld
	try:
		utxos = download_utxos(url)
	except Timeout:
		return json.dumps({'error':'timeout contacting block explorer', 'url':url}), 504, mime_json
	except InvalidResponse as error:
		return json.dumps({'error':'error contacting block explorer', 'url':url, 'status':error.status_code}), 502, mime_json
	except ValueError as error:
		return json.dumps({'error':'bad explorer response format', 'message':str(error), 'url':url}), 424, mime_json
	
	assets = []
	
	for utxo in utxos['addrTxs']:
		asset = utxo['asset']
		value = utxo['value']
		assets.append({'asset':asset, 'value':value})
	
	return json.dumps({'dgld':dgld, 'assets':assets}), 200, mime_json


@app.route('/dgld-bar/<dgld>')
def dgld_bar(dgld):
	"dgld->asset->bar: Takes a DGLD address, returns list of bar refs and masses covered by that address, with their values."
	
	if not is_dgld_address(dgld):
		return json.dumps({'error':'not a dgld address', 'value':dgld}), 400, mime_json
	
	url = UTXOS_API_URL_TEMPLATE % dgld
	try:
		utxos = download_utxos(url)
	except Timeout:
		return json.dumps({'error':'timeout contacting block explorer', 'url':url}), 504, mime_json
	except InvalidResponse as error:
		return json.dumps({'error':'error contacting block explorer', 'url':url, 'status':error.status_code}), 502, mime_json
	except ValueError as error:
		return json.dumps({'error':'bad explorer response format', 'message':str(error), 'url':url}), 424, mime_json
	
	bars = []
	for utxo in utxos['addrTxs']:
		asset = utxo['asset']
		value = utxo['value']
		try:
			bar = asset_map[asset]
			ref = bar['ref']
			mass = bar['mass']
		except KeyError:
			return json.dumps({'error':'bar info not found for the specified asset', 'asset':asset}), 424, mime_json
		bars.append({'asset':asset, 'value':value, 'ref':ref, 'mass':mass})
	
	return json.dumps({'dgld':dgld, 'bars':bars}), 200, mime_json


@app.route('/eth-asset/<eth>')
def eth_asset(eth):
	"eth->asset"
	
	if not is_eth_address(eth):
		return json.dumps({'error':'not an eth address', 'value':eth}), 400, mime_json
	
	eth = eth.lower()
	
	mapping = generate_mapping(eth_balances, locked_assets)
	ethbridge_mapping = dict((_k.lower(), [{'asset':_e[0], 'value':_e[1]} for _e in _v]) for (_k, _v) in mapping.items())
	
	try:
		return json.dumps({'eth':eth, 'assets':ethbridge_mapping[eth]}), 200, mime_json
	except KeyError:
		return json.dumps({'eth':eth, 'assets':[]}), 200, mime_json


@app.route('/eth-bar/<eth>')
def eth_bar(eth):
	"eth->asset->bar"
	
	if not is_eth_address(eth):
		return json.dumps({'error':'not an eth address', 'value':eth}), 400, mime_json
	
	eth = eth.lower()
	
	mapping = generate_mapping(eth_balances, locked_assets)
	ethbridge_mapping = dict((_k.lower(), [{'asset':_e[0], 'value':_e[1]} for _e in _v]) for (_k, _v) in mapping.items())
	
	try:
		asset_allocation = ethbridge_mapping[eth]
	except KeyError:
		return json.dumps({'eth':eth, 'bars':[]}), 200, mime_json
	
	bars = []
	
	print(asset_allocation)
	for entry in asset_allocation:
		asset = entry['asset']
		value = entry['value']
		try:
			bar = asset_map[asset]
			ref = bar['ref']
			mass = bar['mass']
		except KeyError:
			return json.dumps({'error':'bar info not found for the specified asset', 'asset':asset}), 424, mime_json
		bars.append({'asset':asset, 'value':value, 'ref':ref, 'mass':mass})
	
	return json.dumps({'eth':eth, 'bars':bars}), 200, mime_json


@app.route('/eth-balances')
def eth_balances_feed():
	return json.dumps(dict((_k, {'value':_v}) for (_k, _v) in eth_balances.items())), 200, mime_json


@app.route('/locked-assets')
def locked_assets_feed():
	return json.dumps(dict((_k, {'value':_v}) for (_k, _v) in locked_assets.items())), 200, mime_json



def asset_map_updater(asset_map):
	"Download asset map from Amazon every 24 hours. The result is saved into the dict provided as argument. Retry if download failed."
	try:
		while True:
			while True:
				try:
					print("downloading asset map")
					asset_map_new = download_asset_map()
					asset_map.clear()
					asset_map.update(asset_map_new)
				except (Timeout, InvalidResponse, ValueError) as error:
					print("asset map update failed:", error)
					sleep(60)
					continue
				else:
					break
			sleep(60*60*24)
	except KeyboardInterrupt:
		print()


def eth_balances_updater(eth_balances):
	"Look for new transactions on Ethereum network and update ETH balances every 60 seconds. The result is saved into the dict provided as argument. Change provider and retry if download failed."
	global w3, wdgld_contract
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
				wdgld_contract = None
				
				while not w3 or not w3.isConnected() or wdgld_contract == None:
					provider_url = choice(PROVIDER_URLS)
					print("connecting to eth node")
					connect_to_eth(provider_url)
					
					if w3 and w3.isConnected():
						print("getting contract")
						get_contract()
					else:
						print("not connected")
				
				print("resetting balances")
				reset_balances()
				
				while synchronized():
					print("update balances", w3.eth.blockNumber - balances_block)
					update_balances()
					
					if w3.eth.blockNumber <= balances_block + 6:
						print("balances up to date")
						eth_balances.clear()
						eth_balances.update(dict(balances_list()))
						
						sleep(60)
				
				print("lost synchronization")
			
			except AssertionError as error:
				print("error:", error)
				continue
	
	except KeyboardInterrupt:
		print()



def locked_assets_updater(locked_assets):
	"Download the list of assets in Ethbridge every 60 seconds from DGLD explorer. Save results into the dict provided as argument. Retry if download failed."
	try:
		while True:
			try:
				print("downloading locked assets")
				assets = download_locked_assets(ETHBRIDGE_DGLD_ADDRESS)
			except (Timeout, InvalidResponse, ValueError) as error:
				print("error downloading assets locked in ethbridge", error)
			else:
				print("locked assets downloaded")
				locked_assets.clear()
				locked_assets.update(assets)
				sleep(60)
	
	except KeyboardInterrupt:
		print()



if __name__ == '__main__':
	from multiprocessing import Process, Manager
	
	with Manager() as manager:
		# proxy objects to share state between processes
		asset_map = manager.dict()
		eth_balances = manager.dict()
		locked_assets = manager.dict()
		
		# spawn updaters
		asset_map_proc = Process(target=asset_map_updater, args=(asset_map,))
		eth_balances_proc = Process(target=eth_balances_updater, args=(eth_balances,))
		locked_assets_proc = Process(target=locked_assets_updater, args=(locked_assets,))
		
		asset_map_proc.start()
		eth_balances_proc.start()
		locked_assets_proc.start()
		
		try:
			# start the WSGI server
			app.run(host=WSGI_IP, port=WSGI_PORT, debug=DEBUG_FLAG)
		except KeyboardInterrupt:
			print()


