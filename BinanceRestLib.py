import threading
import time
import ssl
import json

from urllib import request
from urllib import parse

import hmac
import hashlib

# need to use python-requests instead of the dumm original urlopen function
import requests



# basic test with timestamp
baseUrl = 'https://api.binance.com'

# create a non verified SSL context
context = ssl._create_unverified_context()

# create header of HTTPs connection with API key
request_header = ({'Accept': 'application/json',
                    'User-Agent': 'binance/python',
                    'X-MBX-APIKEY': APIKey})

# time offset between server time and local time
time_offset = 0

# standard recv window
recvWindow = 5000

class getPriceThread (threading.Thread):
   def __init__(self, threadID, name, symbol, coin, volumn):
      threading.Thread.__init__(self)
      self.threadID = threadID
      self.name = name
      self.symbol = symbol
      self.coin = coin
      self.volumn = volumn
      self.price = {}
   def run(self):
    #   print('Start thread of ' + self.name + '@' + str(time.time()))
      self.price = getCurrentPrice(self.symbol, self.coin, self.volumn)
    #   print("Price of %s and %s is %f" %(self.symbol, self.coin, self.price))
    #   print('End thred of ' + self.name + '@' + str(time.time()))


def getServerTime():
    # basic test with timestamp
    urlTime = baseUrl+ '/api/v1/time'
    response = requests.get(urlTime)
    print(response.json())
    return response.json()

def getServerTimeOffset():
    local_time = int(time.time()*1000)
    server_time = getServerTime()['serverTime']
    time_offset = server_time - local_time
    return time_offset

def getCurrentPriceTicker(symbol, ref_coin):
    urlPrice = baseUrl + '/api/v3/ticker/price?symbol=' + symbol + ref_coin
    price_json = request.urlopen(urlPrice, context=context).read().decode('utf-8')
    price = float(json.loads(price_json)['price'])
    return price

def getCurrentPrice(symbol, ref_coin, volumn):
    param = {}
    param['symbol'] = symbol + ref_coin
    param['limit'] = 5
    # Call service depth to get the current maker price
    depth = getService('depth',param)
    # print(depth)
    
    price = {}
    # consider also the required volumn
    remain_buy_volumn = volumn['buy']
    remain_sell_volumn = volumn['sell']
    temp_buy_price = 0
    temp_sell_price = 0

    for i in range(5):
        temp = remain_buy_volumn - float(depth['asks'][i][1])
        # if the current price can't cover the remain volumn
        if temp>0:
            # consider also the next order
            temp_buy_price += float(depth['asks'][i][1])*float(depth['asks'][i][0])
            remain_buy_volumn = temp
            # print("Sepecial case! buy volumn remaining for %s is %f" %(symbol+ref_coin,remain_buy_volumn))
            # print(depth)
        else:
            temp_buy_price += remain_buy_volumn*float(depth['asks'][i][0])
            remain_buy_volumn = temp
            break
    if remain_buy_volumn<=0:
        price['asks_vol'] = temp_buy_price/volumn['buy']
    else:
        price['asks_vol'] = 'NAN'

    for i in range(5):
        temp = remain_sell_volumn - float(depth['bids'][i][1])
        # if the current price can't cover the remain volumn
        if temp>0:
            temp_sell_price += float(depth['bids'][i][1])*float(depth['bids'][i][0])
            remain_sell_volumn = temp
            # print("Sepecial case! sell volumn remaining for %s is %f" %(symbol+ref_coin,remain_sell_volumn))
            # print(depth)
        else:
            temp_sell_price += remain_sell_volumn*float(depth['bids'][i][0])
            remain_sell_volumn = temp
            break
    if remain_sell_volumn<=0:
        price['bids_vol'] = temp_sell_price/volumn['sell']
    else:
        price['bids_vol'] = 'NAN'

    # TODO 2: consider also the second/third price
    # price['sell'] = float(depth['bids'][0][0])
    # price['buy'] = float(depth['asks'][0][0])

    # return also the sell_1 (bids_1) price
    price['bids_1'] = float(depth['bids'][0][0])
    # return also the buy_1 (asks_1) price
    price['asks_1'] = float(depth['asks'][0][0])

    return price

def getExchangeInfo():
    exchangeUrl = baseUrl + '/api/v1/exchangeInfo'
    exchangeInfo = requests.get(exchangeUrl).json()
    return exchangeInfo

def getSignature(query_string):
    # create a new hmac object with private key and SHA-256
    hmac_string = hmac.new(privateKey.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256)
    return hmac_string.hexdigest()

def getBalance(coin_list, time_offset):
    # create restful parameters
    param = {}
    param['recvWindow'] = 5000
    param['timestamp'] = int(time.time()*1000)+time_offset
    result = getSignedService('account', param)
    balance = result['balances']
    # loop for all required coins, find the balance and save them
    free = {}
    for coin in coin_list:
        # use generator expression to find out the key value from a list in dictionary
        free[coin] = next(item for item in balance if item['asset']==coin)['free']
    return free

def getSignedService(service_name, param):
    # prase json formed parameter to query string
    query_string = parse.urlencode(param)
    # calcualte signgature with private key and query string
    sign = getSignature(query_string)
    # build the calling post url with diff. servers name
    urlUserData = baseUrl + '/api/v3/' + service_name + '?' + query_string + '&signature=' + sign
    # post_request = request.Request(urlUserData,headers=request_header)
    # response = request.urlopen(post_request, context=context)
    # return response.read()

    response = requests.get(urlUserData, headers=request_header)
    return response.json()

def getService(service_name, param):
    # prase json formed parameter to query string
    query_string = parse.urlencode(param)
    # build the calling post url with diff. servers name
    urlUserData = baseUrl + '/api/v1/' + service_name + '?' + query_string
    response = requests.get(urlUserData, headers=request_header)
    return response.json()

def cancelOrder(symbol, coin, orderID, time_offset):
    param = {}
    param['symbol'] = symbol + coin
    param['orderId'] = orderID
    param['recvWindow'] = recvWindow
    param['timestamp'] = int(time.time()*1000) + time_offset
    # prase json formed parameter to query string
    query_string = parse.urlencode(param)
    # calcualte signgature with private key and query string
    sign = getSignature(query_string)
    # create post url
    orderUrl = baseUrl + '/api/v3/order?' + query_string + '&signature=' + sign

    response = requests.delete(orderUrl, headers=request_header)
    return response.json()

def createMarketOrder(symbol, coin, side, quantity, time_offset):
    # prepare the post parameters
    param = {}
    param['symbol'] = symbol + coin
    param['side'] = side
    param['type'] = 'MARKET'
    param['newOrderRespType'] = 'FULL'
    param['quantity'] = quantity
    param['recvWindow'] = recvWindow
    # add time offset between the server and local
    param['timestamp'] = int(time.time()*1000) + time_offset
    # prase json formed parameter to query string
    query_string = parse.urlencode(param)
    # calcualte signgature with private key and query string
    sign = getSignature(query_string)
    # add signature back to the parameter
    param['signature'] = sign

    # create post url
    orderUrl = baseUrl + '/api/v3/order'

    # call post request with header including API key
    response = requests.post(orderUrl, data=param, headers=request_header)
    return response.json()

def createLimitOrder(symbol, coin, side, quantity, price, time_offset):
    # prepare the post parameters
    param = {}
    param['symbol'] = symbol + coin
    param['side'] = side
    param['type'] = 'LIMIT'
    param['timeInForce'] = 'GTC'
    param['newOrderRespType'] = 'FULL'
    param['quantity'] = quantity
    param['price'] = price
    param['recvWindow'] = recvWindow
    # add time offset between the server and local
    param['timestamp'] = int(time.time()*1000) + time_offset
    # prase json formed parameter to query string
    query_string = parse.urlencode(param)
    # calcualte signgature with private key and query string
    sign = getSignature(query_string)
    # add signature back to the parameter
    param['signature'] = sign

    # create post url
    orderUrl = baseUrl + '/api/v3/order'

    # call post request with header including API key
    response = requests.post(orderUrl, data=param, headers=request_header)
    return response.json()