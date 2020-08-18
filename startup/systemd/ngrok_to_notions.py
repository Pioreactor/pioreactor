# may need to sudo pip3 install notion
from notion.client import NotionClient
import requests
import time
import configparser

r = requests.get("http://localhost:4040/api/tunnels")
public_url = None


while public_url is None:
    try:
        public_url = r.json()['tunnels'][0]['public_url']
    except:
        time.sleep(10)

config = configparser.ConfigParser()
config.read('~/mobidostat/startup/systemd/creds.ini')
notions_token = config['notions']['token']

client = NotionClient(token_v2=notions_token)
page = client.get_block("https://www.notion.so/camdp/RaspberryPis-d8dfbc52736d4bd4b4551cddad2ea38d#2d50a0cdd45443449d02385374f5fc5a")
page.title = public_url
