# Bar Mapper

A web service displaying physical bars legally owned by holders of Ethereum wDGLD token.


## Requirements

Python 3, Flask, Web3.py, SolcX

```
pip3 install flask
pip3 install web3
pip3 install py-solc-x
```


## Interface to Ethereum

The service uses Infura as a bridge to Ethereum network. You need to register a project in Infura and provide an API link.
Other providers may be used instead of Infura, or a local Ethereum node, but Infura is recommended.

More than one provider can be used. The mapper will choose one randomly and switch when it has lost connection.

Edit the provider list in the `mapper.py` file, parameter name `PROVIDER_URLS`.


## Running

To start the service, run the script `mapper.py`. The script searches for neccessary files in the directory it has been run from.

The service runs as an WSGI app under the port 5000 by default. The port setting can be changed (edit the `mapper.py` file, parameter `WSGI_PORT`).
In production mode, the service should be hosted through a web server. Change the IP address the service is running at to
an address accessible by the web server (127.0.0.1 if the server is running on the same machine), parameter `WSGI_IP`. Never run a production
server with the `DEBUG_FLAG` enabled, as it will reveal stack traces.

```
cd /path/to/bar/mapper
./mapper.py # start the service under default port 5000
curl http://127.0.0.1:5000/
```

Webserver: redirect a public URL to `http://127.0.0.1:5000/`.


## wDGLD contract version

On startup, the script will try to compile the wDGLD contract. If any problem occurs (most likely due to version mismatch), the service will not
start. The contract is contained in the directory `dgld-smart-contracts`. The OpenZeppelin header files need to be stored in the directory
`openzeppelin-solidity`. If the wDGLD contract is ever updated, it the new version need to be provided to the service. The contract is hosted
in the repository `https://github.com/commerceblock/dgld-smart-contracts`. The OpenZeppelin headers must be the same version that was used to
compile the contract deployed to the Ethereum network. Also, it is recommended to use the same version of the Solc compiler.


## Ethbridge and the mapping definition

This is an Ethereum contract managing the wDGLD ERC-20 token. The contract address is `0x123151402076fc819b7564510989e475c9cd93ca`.
The contract is in backed by DGLD tokens under the address `gDxdzHvfK2a9ARMQQASJqCQ9K47SNUeiot`.

The mapping between wDGLD tokens and asset ids is defined as follows:

The list of all holders of wDGLD tokens is made, sorted by the Eth address (case-insensitive). The list of all DGLD addresses
locked in Ethbridge is made. The list of asset ids held by those addresses is derived. The list is sorted by token id.

An ETH address holds the fraction of the token corresponding to its position in the list.


## Web sources

1. Infura interface to Ethereum mainnet.

The source needed to create the list of wDGLD holders. An Infura project needs to be set up prior.

URL: https://mainnet.infura.io/v3/<infura_project_id>

2. DGLD block explorer.

The source needed to obtain the list of asset ids in Ethbridge. The list is constructed from UTXO data.
Only the Ethbridge DGLD address is queried. The source is checked every 60 seconds.

URL: https://explorer.dgld.ch/api/address/utxos/<dgld_address>

3. Physical bar mapping.

This is a static file specifying the mapping between asset ids and physical bar ids. The source is checked
every 24 hours.

URL: https://s3.eu-west-1.amazonaws.com/gtsa-mapping/map.json


## Feeds provided by the mapper

All feeds are in JSON format.

* /asset-bar/<asset_id>
Physical bar data for the specified asset id.
Format: `{'asset':asset_id, 'ref':bar_id, 'mass':float}`

* /dgld-asset/<dgld_address>
List of asset ids for the specified DGLD address. In practice, only the Ethbridge DGLD address is used, however
any DGLD address may be queried this way.
Format: `{'dgld':dgld_address, 'assets':[{'asset':asset_id, 'value':float}, ...]}`

* /dgld-bar/<dgld_address>
List of physical bar ids for the specified DGLD address. This feed combines data from the physical bar mapping and
DGLD block explorer.
Format: `{'dgld':dgld_address, 'bars':[{'asset':asset_id, 'ref':bar_id, 'mass':float, 'value':float}, ...]}`

* /eth-asset/<eth_address>
List of asset ids (and values) for the specified ETH address. The mapping is defined above.
Format: `{'eth':eth_address, 'assets':[{'asset':asset_id, 'value':float}, ...]}`

* /eth-bar/<eth_address>
List of physical bars (or fractions thereof) for the specified ETH address. The mapping is defined above. This feed
combines data from all 3 sources.
Format: `{'dgld':dgld_address, 'bars':[{'asset':asset_id, 'ref':bar_id, 'mass':float, 'value':float}, ...]}`

* /eth-balances
Balances of all ETH accounts holding the wDGLD token. Unlike all other feeds, this instance returns the value as
integer, in the basic units.
Format: `{eth_address_1: {'value':int}, eth_address_2: {'value':int}, ...}`

* /locked-assets
List of asset ids locked in Ethbridge. The Ethbridge DGLD address is provided above. The information is taken from
DGLD block explorer.
Format: `{asset_id_1: {'value':float}, asset_id_2: {'value':float}, ...}`


## Frontend

The service provides a simple frontend, where it is possible to query the list of asset ids owned by ETH address.

* `index.html`
The main HTML file, served under the default HTTP path.

* `style.css`
CSS stylesheet used by the `index.html` file.

* `client.py`
Client-side Python script, included by `index.html`. Interpreted in the browser by Brython.

* `brython.js`, `brython_stdlib.js`
Python implementation in Javascript. Must be served from the same address as `index.html` due to browsers' security
policy. This may be changed using CORS header.



