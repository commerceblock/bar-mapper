

from browser import window, document, ajax
from browser.html import maketag
from hashlib import sha256
import json


tr = maketag('tr')
td = maketag('td')
th = maketag('th')
thead = maketag('thead')
tbody = maketag('tbody')


def get_mapping(widget):
	def received(src):
		print("received", src.status)
		result = json.loads(src.text)
		
		if 'error' in result:
			document['error_message'] <= result['error']
			return
		
		table_body = tbody()
		
		for bar in result['bars']:
			asset = bar['asset']
			value = bar['value']
			ref = bar['ref']
			mass = bar['mass']
			
			table_body <= tr(td(asset) + td(value) + td(ref) + td(mass))
		
		document['bar_mapping'] <= thead(tr(th("asset") + th("value") + th("ref") + th("mass"))) + table_body
	
	print("get_mapping")
	document['error_message'].innerHTML = ""
	document['bar_mapping'].innerHTML = ""
	dgld_address = document['dgld_address'].value
	ajax.get(f'/dgld-bar/{dgld_address}', blocking=False, oncomplete=received)

document['get_mapping'].bind('click', get_mapping)

