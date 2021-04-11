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

    def __init__(self,username,password,host="https://lidl-api.prod.vodafone.aws-arvato.com"):
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

    def get_param(self, query):
        self.refreshAccessToken()
        data = self.client.execute(query=query)
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
        return self.get_param(query)['currentCustomer']['balance']

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
        data = self.get_param(query)
        r = {}
        r["consumed"] = data['consumptions']['consumptionsForUnit'][0]["consumed"]
        r["max"] = data['consumptions']['consumptionsForUnit'][0]["max"]
        r["unit"] = data['consumptions']['consumptionsForUnit'][0]["unit"]
        return r


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
