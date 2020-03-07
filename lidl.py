import sys
from prometheus_client import Counter
from prometheus_client import start_http_server
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.core import REGISTRY
import requests
import re
import os
import time

class LidlCollector(object):
    def collect(self):
        s = requests.Session()
        r0=s.get('https://kundenkonto.lidl-connect.de/login.html')
        m=re.search('name="REQUEST_TOKEN" value="([^"]*)', r0.content.decode('utf8') )
        token = m.group(1)
        r1 = s.post('https://kundenkonto.lidl-connect.de/login.html', {"REQUEST_TOKEN":token, "lastpage": 1, "msisdn_msisdn":msisdn,"password":password})
        
        m=re.search('amount-text">\s+([\d,]+) GB von ([\d,]+) GB verbraucht\s+</div', r1.content.decode('utf8') )
        c = CounterMetricFamily("used_gb", 'GB used')
        c.add_metric(['used'], float(m.group(1).replace(',','.')))
        yield c
        
        t = GaugeMetricFamily("total_gb", 'GB total')
        t.add_metric(['total'], float(m.group(2).replace(',','.')))
        yield t
        
        m=re.search('amount-text">\s+(\d+) Min/SMS von (\d+) Min/SMS verbraucht\s+</div', r1.content.decode('utf8') )
        uu = CounterMetricFamily("used_units", 'Units used')
        uu.add_metric(['used'], int(m.group(1)))
        yield uu
        
        ut = GaugeMetricFamily("total_unity", 'Units total')
        ut.add_metric(['total'], int(m.group(2)))
        yield ut
        
        m=re.search('balance-amount">([\d,]+) &euro;</span>', r1.content.decode('utf8') )
        bal = GaugeMetricFamily("balance", 'balance')
        bal.add_metric(['total'], float(m.group(1).replace(',','.')))
        yield bal


if __name__ == '__main__':
    msisdn = os.environ.get("MSISDN", None)
    password = os.environ.get("PASSWORD", None)
    port = os.environ.get("PORT", 9100)
    
    if msisdn is None or password is None:
        sys.exit(1)
    
    REGISTRY.register(LidlCollector())
    # start the server
    start_http_server(port)
    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        sys.exit()
