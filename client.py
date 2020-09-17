

from browser import window, document, ajax
from browser.html import maketag
from hashlib import sha256
import json


tr = maketag('tr')
td = maketag('td')
th = maketag('th')
table = maketag('table')
thead = maketag('thead')
tbody = maketag('tbody')
a_href = maketag('a')


def fill_table(element_id, url, list_field, fields, first_column, columns, clickability=(lambda x:x)):
	def received(src, args):
		element_id, url, list_field, fields, first_column, columns, clickability = args
		
		result = json.loads(src.text)
		
		if 'error' in result:
			document[element_id] <= result['error']
			return
		
		table_body = tbody()
		
		if list_field:
			lf = result[list_field]
		else:
			lf = result
		
		if isinstance(lf, list):
			lp = range(len(lf))
		else:
			lp = lf
		
		for entry in lp:
			#print(entry)
			values = [td(lf[entry][field]) for field in fields]
			table_body <= tr(sum(values, td(clickability(entry))))
		
		colh = [th(column) for column in columns]
		document[element_id] <= table(thead(tr(sum(colh, th(first_column)))) + table_body)
	
	document[element_id].innerHTML = ""
	ajax.get(url, blocking=False, oncomplete=(lambda args: lambda src: received(src, args))((element_id, url, list_field, fields, first_column, columns, clickability)))


def fill_address(addr):
	def do_fill_address(widget):
		document['eth_address'].value = addr
		get_assets(widget)
	return do_fill_address

def clickable_address(addr):
	link = a_href(addr, href='#mapping_table')
	link.bind('click', fill_address(addr))
	return link


fill_table('eth_balances', '/eth-balances', None, ['value'], 'Address', ['Balance'], clickable_address)

fill_table('locked_assets', '/locked-assets', None, ['value'], 'Token ID', ['Value'])


def get_assets(widget):
	eth = document['eth_address'].value
	fill_table('bar_mapping', f'/eth-asset/{eth}', 'assets', ['asset', 'value'], 'N.', ['Token ID', 'Value'])

document['get_assets'].bind('click', get_assets)

