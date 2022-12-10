from datetime import datetime, timedelta
import os
from prometheus_client import Counter
from prometheus_client import start_http_server
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.core import REGISTRY
from python_graphql_client import GraphqlClient
import requests
import time


# thanks to https://betterprogramming.pub/how-to-refresh-an-access-token-using-decorators-981b1b12fcb9
class LidlAPI():
    host = None
    key = None
    secret = None
    access_token = None
    access_token_expiration = None
    client = None

    def __init__(self,username,password,host="https://api.lidl-connect.de"):
        # the function that is executed when
        # an instance of the class is created
        self.host = host
        self.username = username
        self.password = password

        self.refreshAccessToken()


    def refreshAccessToken(self):
        # the function that is
        # used to request the JWT
        if self.access_token_expiration is None or time.time() > self.access_token_expiration:
            try:
                # build the JWT and store
                # in the variable `token_body`
                token_body = {
                    "grant_type":"password",
                    "client_id":"lidl",
                    "client_secret":"lidl",
                    "username":self.username,
                    "password":self.password
                }
                # request an access token
                request = requests.post("%s/api/token"%self.host,data=token_body)

                # optional: raise exception for status code
                request.raise_for_status()
            except Exception as e:
                raise e
                print(e)
                #return None
            else:
                # assuming the response's structure is
                # {"access_token": ""}
                self.access_token = request.json()['access_token']
                self.access_token_expiration = time.time() + 3500
                self.client = GraphqlClient(
                    endpoint="%s/api/graphql"%self.host,headers={
                    "Content-type": "application/json",
                    "Authorization": "Bearer %s"%self.access_token}
                    )

    def _api_call(self, query, variables=None):
        self.refreshAccessToken()
        if variables is None:
            variables = {}
        data = self.client.execute(query=query, variables=variables)
        return data['data']


    def get_balance(self):
        # Create the query string and variables required for the request.
        query = """
            query balanceInfo {
                currentCustomer {
                    balance
                    __typename
                }
            }
        """
        return self._api_call(query)['currentCustomer']['balance']

    def get_usage(self):

        query = """
            query consumptions {
                consumptions {
                    consumptionsForUnit {
                        consumed
                        unit
                        formattedUnit
                        type
                        description
                        expirationDate
                        left
                        max
                    }
                }
            }
        """
        data = self._api_call(query)
        r = {}
        if len(data['consumptions']['consumptionsForUnit']) > 0:
            r["consumed"] = data['consumptions']['consumptionsForUnit'][0]["consumed"]
            r["max"] = data['consumptions']['consumptionsForUnit'][0]["max"]
            r["unit"] = data['consumptions']['consumptionsForUnit'][0]["unit"]
        else:
            r["consumed"] = 0.0
            r["max"] = 0
            r["unit"] = 'GB'
        return r
    
    def get_calls(self):
        query = """
            query itemisedBills($filter: ItemisedBillFilterInput) {
                currentCustomer {
                    contract {
                        msisdn
                        __typename
                    }
                    itemisedBills(filter: $filter) {
                        actionDate
                        destination
                        details
                        duration
                        fromCountry
                        groupKey
                        id
                        productCode
                        requestorID
                        toCountry
                        typeKey
                        value
                        __typename
                    }
                __typename
                }
            }"""
        variables = {"filter":{
            "from":(datetime.now()-timedelta(days=40)).date().strftime("%d.%m.%Y"),
            "to":datetime.now().date().strftime("%d.%m.%Y")}
        }

        data = self._api_call(query, variables)

        calls_stat = {}
        calls_type = {}
        for item in reversed(data["currentCustomer"]["itemisedBills"]):
            key = item["typeKey"]
            if key not in calls_stat:
                calls_stat[key] = {"duration":0,"units":0, "value":0}
            if key == "CDR": # call
                try:
                    value = int(item["value"])
                    duration = int(item["duration"])
                    units = duration//60+1
                    calls_stat[key]["duration"]+=duration
                    calls_stat[key]["units"]+=units
                    product = item["productCode"]
                    if product not in calls_type:
                        calls_type[product] = {"duration":0}
                    calls_type[product]["duration"]+=duration
                except:
                    print("no duration for", item)
            elif key == "SMS":
                value = int(item["value"])
                calls_stat[key]["value"]+=value
                calls_stat[key]["units"]+=1
            elif key == "SRV": # new booking
                #print("calls data")
                #print(calls_stat)
                #print("reset")
                calls_stat = {}
                calls_type = {}
            elif key in ["CDT"]:
                value = int(item["value"])
                calls_stat[key]["value"]+=value
            else:
                print("unknown record:", item)

        return (calls_stat, calls_type)

class LidlCollector(object):

    api = None

    def __init__(self, api):
        self.api = api

    def collect(self):
        
        usage = self.api.get_usage()

        c = CounterMetricFamily("used_gb", 'GB used')
        c.add_metric(['used'], usage["consumed"])
        yield c

        t = GaugeMetricFamily("total_gb", 'GB total')
        t.add_metric(['total'], usage["max"])
        yield t
        
        calls, types = self.api.get_calls()
        units = GaugeMetricFamily("used_units", 'Units used', labels=["type"])
        for key in calls:
            units.add_metric([key], calls[key]['units'])
        yield units
        
        seconds = GaugeMetricFamily("called_seconds", 'Called Seconds', labels=["network"])
        for net in types:
            seconds.add_metric([net], types[net]['duration'])
        yield seconds

        bal = GaugeMetricFamily("balance", 'balance')
        bal.add_metric(['total'], self.api.get_balance()/100)
        yield bal


if __name__ == '__main__':
    msisdn = os.environ.get("MSISDN", None)
    password = os.environ.get("PASSWORD", None)
    port = os.environ.get("PORT", 9100)
    
    if msisdn is None or password is None:
        sys.exit(1)

    lidl = LidlAPI(msisdn, password)
    col = LidlCollector(lidl)
    REGISTRY.register(col)
    # start the server
    start_http_server(port)
    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        sys.exit()
