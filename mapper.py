#!/usr/bin/python3
#-*- coding:utf-8 -*-


from flask import Flask, request, abort, make_response
from pathlib import Path
import json
from requests import get
from requests.exceptions import Timeout


mime_json = [('Content-Type', 'application/json')]
mime_xhtml = [('Content-Type', 'application/xhtml+xml')]
mime_css = [('Content-Type', 'text/css')]
mime_python = [('Content-Type', 'application/python')]
mime_javascript = [('Content-Type', 'application/javascript')]

#mime_xhtml = [('Content-Type', 'application/xhtml+xml'), ('Cache-Control', 'only-if-cached, max-age=604800')]
#mime_css = [('Content-Type', 'text/css;charset=utf-8'), ('Cache-Control', 'only-if-cached, max-age=604800')]
#mime_python = [('Content-Type', 'application/python;charset=utf-8'), ('Cache-Control', 'only-if-cached, max-age=604800')]
#mime_javascript = [('Content-Type', 'application/javascript;charset=utf-8'), ('Cache-Control', 'only-if-cached, max-age=604800')]


app = Flask('bar_mapper')


asset_map_url = 'https://s3.eu-west-1.amazonaws.com/gtsa-mapping/map.json'
utxos_api_url_template = 'https://explorer.dgld.ch/api/address/utxos/%s'
request_timeout = 4 # default timeout (seconds) for all http requests

asset_map = {}


def is_dgld_address(dgld):
	return True


def is_asset_id(asset):
	return True


def get_asset_map():
	global asset_map
	try:
		asset_map_request = get(asset_map_url, timeout=request_timeout)
	except Timeout:
		pass # TODO: warning, retry
	if asset_map_request.status_code == 200:
		try:
			asset_map_result = asset_map_request.json()
			asset_map = {}
			for number, entry in asset_map_result['assets'].items():
				asset = entry['tokenid']
				ref = entry['ref']
				mass = entry['mass']
				asset_map[asset] = {'asset':asset, 'ref':ref, 'mass':mass}
		except ValueError:
			pass # TODO: warning, retry
	else:
		pass # TODO: warning, retry


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
	if not is_asset_id(asset):
		return json.dumps({'error':'not an asset id', 'value':asset}), 415, mime_json
	
	bar = asset_map[asset]
	ref = bar['ref']
	mass = bar['mass']
	return json.dumps({'asset':asset, 'ref':ref, 'mass':mass}), 200, mime_json


@app.route('/dgld-asset/<dgld>')
def dgld_asset(dgld):
	if not is_dgld_address(dgld):
		return json.dumps({'error':'not a dgld address', 'value':dgld}), 400, mime_json
	
	url = utxos_api_url_template % dgld
	
	try:
		utxos_response = get(url, timeout=request_timeout)
	except Timeout:
		return json.dumps({'error':'timeout contacting block explorer', 'url':url}), 504, mime_json
	
	if utxos_response.status_code != 200:
		return json.dumps({'error':'error contacting block explorer', 'url':url, 'status':utxos_response.status_code}), 502, mime_json
	
	try:
		utxos = utxos_response.json()
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
	if not is_dgld_address(dgld):
		return json.dumps({'error':'not a dgld address', 'value':dgld}), 400, mime_json
	
	url = utxos_api_url_template % dgld
	
	try:
		utxos_response = get(url, timeout=request_timeout)
	except Timeout:
		return json.dumps({'error':'timeout contacting block explorer', 'url':url}), 504, mime_json
	
	if utxos_response.status_code != 200:
		return json.dumps({'error':'error contacting block explorer', 'url':url, 'status':utxos_response.status_code}), 502, mime_json
	
	try:
		utxos = utxos_response.json()
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
			ref = ''
			mass = 0
		bars.append({'asset':asset, 'value':value, 'ref':ref, 'mass':mass})
	
	return json.dumps({'dgld':dgld, 'bars':bars}), 200, mime_json



if __name__ == '__main__':
	get_asset_map() # TODO: asset map downloaded only on startup, implement periodic checks
	
	port = 5000
	
	# plain http, development
	#app.run(host='127.0.0.1', port=port, debug=True)
	
	# plain http, production
	#app.run(host='0.0.0.0', port=port, debug=False)
	
	# https, production
	import sys
	import ssl
	from gevent import pywsgi
	from geventwebsocket.handler import WebSocketHandler
	
	ip = '127.0.0.1'
	certfile = 'haael.net.crt' # certfile with privkey
	password = sys.argv[1] # privkey password
	#sys.argv[1] = "" # hide password from ps
	
	context = ssl.SSLContext()
	context.load_cert_chain(certfile=certfile, password=password)
	server = pywsgi.WSGIServer((ip, port), app, handler_class=WebSocketHandler, ssl_context=context)
	
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		print()



