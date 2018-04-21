import ssl
import json
import time
import datetime
import threading
import math

import BinanceRestLib

class TriangleStrategy(object):
    # minimum trading volumn for the reference coin
    # BTC: 0.001; ETH: 0.01
    minNotional = 0.001

    # standard volumn used for triangle strategy
    buy_volumn = minNotional * 1.2

    # minimum trading volumn unit for the symbol|ref_coin[0], symbol|ref_coin[1] and ref_coin[1]|ref_coin[0]
    # minQty = [0.01, 0.01, 0.01]

    # minPrice = [0.000001, 0.0001, 0.000001]
    # price_precise = [int(-math.log10(x)) for x in minPrice]

    # volumn toloranz (0.05%) to match the request delay, that some one has already buy/sell with the detected price
    volumn_toloranz = 1.1

    # define trigger interval for trading
    trigger_threshold = 1.002
    def __init__(self, symbol, coin):
        self.symbol = symbol
        self.coin = coin
        self.price = {}
        self.time_offset = BinanceRestLib.getServerTimeOffset()

        self.balance_coin_list = coin
        self.balance_coin_list.append(symbol)
        self.begin_balance = BinanceRestLib.getBalance(self.balance_coin_list, self.time_offset)
        self.last_balance = self.begin_balance
        self.saveAccountInfo()

        # get needed Exchange Info
        self.getExchangeInfo()
        print(self.minQty)
        print(self.minPrice)

        # Use traiding minQty to ask first price, so that the requried buy/sell volumn can be estimated
        self.volumn = []
        for i in range(3):
            self.volumn.append({'buy':self.minQty[i],'sell':self.minQty[i]})

        # get all tradeable symbol from the list
        self.getSymbolList()
    
    def getExchangeInfo(self):
        exchangeInfo = BinanceRestLib.getExchangeInfo()
        # update exchange info in local
        # file_out = open('C:/Users/Cibobo/Documents/Coins/Python/ExchangeInfo.txt','w+')
        # json.dump(exchangeInfo, file_out)
        # file_out.close()

        # minimum trading volumn unit for the symbol|ref_coin[0], symbol|ref_coin[1] and ref_coin[1]|ref_coin[0]
        self.minQty = []
        # minimum trading price unit for the symbol|ref_coin[0], symbol|ref_coin[1] and ref_coin[1]|ref_coin[0]
        self.minPrice = []

        # get exchange info from symbol|ref_coin[0]
        # get all filters for the target trading symbol
        filters = next(item for item in exchangeInfo['symbols'] if item['symbol'] == str(self.symbol+self.coin[0]))['filters']
        self.minPrice.append(float(filters[0]['minPrice']))
        self.minQty.append(float(filters[1]['minQty']))

        # get exchange info from symbol|ref_coin[1]
        filters = next(item for item in exchangeInfo['symbols'] if item['symbol'] == str(self.symbol+self.coin[1]))['filters']
        self.minPrice.append(float(filters[0]['minPrice']))
        self.minQty.append(float(filters[1]['minQty']))

        # get exchange info from ref_coin[1]|ref_coin[0]
        filters = next(item for item in exchangeInfo['symbols'] if item['symbol'] == str(self.coin[1]+self.coin[0]))['filters']
        self.minPrice.append(float(filters[0]['minPrice']))
        self.minQty.append(float(filters[1]['minQty']))

        # calculate the precise
        self.price_precise = [int(-math.log10(x)) for x in self.minPrice]

    def saveAccountInfo(self):
        file_out = open('AccountInfo.log','a')
        # save date time
        file_out.write(str(datetime.datetime.now())+'\n')
        file_out.write(str(time.time())+'\n')
        # save begin balance
        json.dump(self.begin_balance, file_out)
        file_out.write('\n\n')
        file_out.close()

    def getTrianglePrice(self):   
        # Create 3 threads to get the 3 prices of triangle trading parallel
        thread1 = BinanceRestLib.getPriceThread(1, "Thread-1", self.symbol, self.coin[0], self.volumn[0])
        thread2 = BinanceRestLib.getPriceThread(2, "Thread-2", self.symbol, self.coin[1], self.volumn[1])
        thread3 = BinanceRestLib.getPriceThread(3, "Thread-3", self.coin[1], self.coin[0], self.volumn[2])

        # Start new Threads
        thread1.start()
        thread2.start()
        thread3.start()

        # Wait for all threads to complete
        thread1.join()
        thread2.join()
        thread3.join()

        # Get the price from thread back and calculate the triangle price
        self.price['direct_buy'] = thread1.price['asks_vol']
        self.price['direct_sell'] = thread1.price['bids_vol']
        # Add sell_1 price for limit trading
        self.price['direct_sell_1'] = thread1.price['bids_1']

        self.price['between_buy'] = thread2.price['asks_vol']
        self.price['between_sell'] = thread2.price['bids_vol']
        # Add buy_1 price for limit between sell
        self.price['between_buy_1'] = thread2.price['asks_1']

        self.price['rate_buy'] = thread3.price['asks_vol']
        self.price['rate_sell'] = thread3.price['bids_vol']
        # Add buy_1 price for limit rate sell
        self.price['rate_buy_1'] = thread3.price['asks_1']

        # Two trading directions are possible:
        # 1. coin[0] --> coin[1](between) --> symbol --> coin[0]: call BBS (buy buy sell)
        # 2. coin[0] --> symbol --> coin[1](between) --> coin[0]: call BSS (buy sell sell)
        # Calculate BBS price and win
        self.price['BBS_price'] = self.price['between_buy']*self.price['rate_buy'] 
        self.price['BBS_win'] = self.price['direct_sell']/self.price['BBS_price']
        # Calculate BSS price and win
        self.price['BSS_price'] = self.price['between_sell']*self.price['rate_sell'] 
        self.price['BSS_win'] = self.price['BSS_price']/self.price['direct_buy']

        #TODO Test Code
        # self.price['BBS_win'] = self.price['BSS_price']/self.price['direct_buy']
        # self.price['BSS_win'] = self.price['BSS_price']/(self.price['direct_sell']+0.00001)

        self.price_time = int(time.time()*1000)+self.time_offset

        # Prepare the volumn for the next price request
        symoble_buy = self.buy_volumn*self.price['direct_buy']
        symbole_sell =  self.buy_volumn*self.price['direct_sell']
        # Direct trading volumn
        self.volumn[0]['buy'] = symoble_buy*self.volumn_toloranz
        self.volumn[0]['sell'] = symbole_sell*self.volumn_toloranz

        # Between trading volumn
        self.volumn[1]['buy'] = symoble_buy*self.price['between_buy']*self.volumn_toloranz
        self.volumn[1]['sell'] = symoble_buy*self.price['between_sell']*self.volumn_toloranz

        # Rate trading volumn
        self.volumn[2]['buy'] = (self.buy_volumn/self.price['rate_buy'])*self.volumn_toloranz
        self.volumn[2]['sell'] = (self.buy_volumn/self.price['rate_sell'])*self.volumn_toloranz

    # Use limit Buy instead of the Market Buy to increasee the win area
    def triangleTradingLimit(self):
        # trading fee
        fee_standard = 0.0005
        fee = [] 

        # recalculate the buy price and win rate with sell price (bid_1) + minPrice allowed by platform
        # consider only BSS mode firstly
        self.price['direct_buy'] = round(float(self.price['direct_sell_1'] + self.minPrice[0]),self.price_precise[0])
        self.price['BSS_win'] = self.price['BSS_price']/self.price['direct_buy']

        # print(self.price, " @", self.price_time)

        # in case the BSS minuse handling fee (0.15%) is still cheeper
        if self.price['BSS_win'] > self.trigger_threshold:
            self.trading_begin_time = int(time.time()*1000)+self.time_offset

            # because of the minimum quantity of the trading, calculate how much target Coin(symbol) should be buy with triangle price
            self.cal_buy_volumn_symbol = self.buy_volumn/self.price['direct_buy']
            self.real_buy_volumn_symbol = (int(self.cal_buy_volumn_symbol/self.minQty[0]))*self.minQty[0]

            # caclulate how much between reference coin is needed based on real buying volumn
            self.cal_trading_volumn_between = self.real_buy_volumn_symbol*self.price['between_sell']
            # use round up integer to calculate the needed between reference coin volumn
            self.real_trading_volumn_between = (math.ceil(self.cal_trading_volumn_between/self.minQty[2]))*self.minQty[2]

            # buy target coin with direct reference coin in Limit Trading
            self.response_1 = BinanceRestLib.createLimitOrder(self.symbol,self.coin[0],"BUY",self.real_buy_volumn_symbol,self.price['direct_buy'],self.time_offset)
            # self.response_1 = BinanceRestLib.createLimitOrder('NANO','ETH','BUY',0.99,0.012,self.time_offset)
            fee.append(self.real_buy_volumn_symbol*fee_standard*self.price['direct_buy'])
            print(json.dumps(self.response_1, indent=4))
            
            # get the order id
            orderId = self.response_1['orderId']

            order_param = {}
            order_param['symbol'] = self.symbol + self.coin[0]
            order_param['orderId'] = orderId
            # oder_param['recvWindow'] = 5000
            order_param['timestamp'] = int(time.time()*1000)+self.time_offset
            # wait a small time interval, until the limit trad is taken by the others
            for i in range(2):
                # check the current trading price in a separte thread
                thread2 = BinanceRestLib.getPriceThread(2, "Thread-2", self.symbol, self.coin[1], self.volumn[1])
                thread2.start()

                self.limit_order = BinanceRestLib.getSignedService("order",order_param)
                # if the order is filled, complete the triangle trading
                if self.limit_order['status'] == "FILLED":
                    # check whether with there is still win rate with the current sell price, if not create a limit sell
                    self.triangleTradingSell(thread2)

                    return 1
                print("End of %dth loop" %(i))

            # check the current trading price in a separte thread, in case the not complated cancel
            thread2 = BinanceRestLib.getPriceThread(2, "Thread-2", self.symbol, self.coin[1], self.volumn[1])
            thread2.start()

            # if the limit trading is not taken by others, cancel it
            self.cancel_limit_order = BinanceRestLib.cancelOrder(self.symbol,self.coin[0],orderId,self.time_offset)
            print(json.dumps(self.cancel_limit_order, indent=4))
            
            # some times the trading is already executed, in this case a error code will be returned
            if 'code' in self.cancel_limit_order:
                print("Special Case: the trading is already filled. Complete the rest selling phase")
                
                # create a limit sell order if the price is change too much
                self.triangleTradingSell(thread2)

                return 1

        self.trading_end_time = int(time.time()*1000)+self.time_offset
        return 0

    # Use limit Direct Buy and also limit sell of between coin
    def triangleTradingLimitTwice(self):
        # recalculate the direct buy price with sell price (bid_1) + minPrice allowed by platform
        self.price['direct_buy'] = round(float(self.price['direct_sell_1'] + self.minPrice[0]),self.price_precise[0])
        # recalculate the between sell price with buy price (ask_1) - minPrice allowed by platform
        self.price['between_sell'] = round(float(self.price['between_buy_1'] - self.minPrice[1]*3),self.price_precise[1])
        # Calculate BSS price and win
        self.price['BSS_price'] = self.price['between_sell']*self.price['rate_sell'] 
        self.price['BSS_win'] = self.price['BSS_price']/self.price['direct_buy']

        # print(self.price, " @", self.price_time)

        # in case the BSS minuse handling fee (0.15%) is still cheeper
        if self.price['BSS_win'] > self.trigger_threshold:
            self.trading_begin_time = int(time.time()*1000)+self.time_offset

            # because of the minimum quantity of the trading, calculate how much target Coin(symbol) should be buy with triangle price
            self.cal_buy_volumn_symbol = self.buy_volumn/self.price['direct_buy']
            self.real_buy_volumn_symbol = (int(self.cal_buy_volumn_symbol/self.minQty[0]))*self.minQty[0]

            # caclulate how much between reference coin is needed based on real buying volumn
            self.cal_trading_volumn_between = self.real_buy_volumn_symbol*self.price['between_sell']
            # use round up integer to calculate the needed between reference coin volumn
            # self.real_trading_volumn_between = (math.ceil(self.cal_trading_volumn_between/self.minQty[2]))*self.minQty[2]

            # use round instead of ceil to balance the volumn of Between Coin and Main Coin
            between_volumn_precise = int(-math.log10(self.minQty[2]))
            self.real_trading_volumn_between = round(self.cal_trading_volumn_between,between_volumn_precise)
            
            # buy target coin with direct reference coin in Limit Trading
            self.response_1 = BinanceRestLib.createLimitOrder(self.symbol,self.coin[0],"BUY",self.real_buy_volumn_symbol,self.price['direct_buy'],self.time_offset)

            print(json.dumps(self.response_1, indent=4))
            
            # get the order id
            orderId = self.response_1['orderId']

            order_param = {}
            order_param['symbol'] = self.symbol + self.coin[0]
            order_param['orderId'] = orderId
            # oder_param['recvWindow'] = 5000
            
            # wait a small time interval, until the limit trad is taken by the others
            for i in range(2):
                order_param['timestamp'] = int(time.time()*1000)+self.time_offset
                self.limit_order = BinanceRestLib.getSignedService("order",order_param)
                # if the order is filled, complete the triangle trading
                if self.limit_order['status'] == "FILLED":
                    # finish the selling process
                    self.triangleTradingSellLimit()
                    
                    return 1

                print("End of %dth loop" %(i))

            # if the limit trading is not taken by others, cancel it
            self.cancel_limit_order = BinanceRestLib.cancelOrder(self.symbol,self.coin[0],orderId,self.time_offset)
            print(json.dumps(self.cancel_limit_order, indent=4))
            
            # some times the trading is already executed, in this case a error code will be returned
            if 'code' in self.cancel_limit_order:
                print("Special Case: the trading is already filled. Complete the rest selling phase")
                # finish the selling process
                self.triangleTradingSellLimit()

                return 1
            
            # check whether some part of the trading is already completed before cancel
            # get the current price
            thread1 = BinanceRestLib.getPriceThread(1, "Thread-1", self.symbol, self.coin[0], self.volumn[0])
            thread1.start()

            order_param['timestamp'] = int(time.time()*1000)+self.time_offset
            self.cancel_order = BinanceRestLib.getSignedService("order",order_param)
            thread1.join()

            # calculate the trading price
            cancel_sell_price = round(float(thread1.price['asks_1'] - self.minPrice[0]),self.price_precise[0])

            # if only a part is completed and this part is bigger than the minimum Notional
            if (float(self.cancel_order['executedQty']) < float(self.cancel_order['origQty'])) and (float(self.cancel_order['executedQty'])*cancel_sell_price > self.minNotional):
                   
                # create a limit trade to sell all target coin back to coin[0], with the sell_1 price
                self.limit_order = BinanceRestLib.createLimitOrder(self.symbol,self.coin[0],"SELL",self.cancel_order['executedQty'],cancel_sell_price,self.time_offset)
                
                order_param['orderId'] = self.limit_order['orderId']
                # wait until the trading is completed
                while True:
                    time.sleep(1)
                    # print("Waiting limit sell for target coin ...")
                    order_param['timestamp'] = int(time.time()*1000)+self.time_offset
                    self.limit_order = BinanceRestLib.getSignedService("order",order_param)
                    if 'status' in self.limit_order:
                        if self.limit_order['status'] == "FILLED":
                            break
                        # if the trading is cancelled manually, wait 5 min for the next rund
                        if self.limit_order['status'] == "CANCELED":
                            print("Cancel the trading and sell the coin manually")
                            time.sleep(300)
                            break
                    else:
                        print("Unknown status:")
                        print(json.dumps(self.limit_order, indent=4))

                print(json.dumps(self.cancel_order, indent=4))  
                print(json.dumps(self.limit_order, indent=4))  

        self.trading_end_time = int(time.time()*1000)+self.time_offset
        return 0

    def triangleTrading(self):
        # trading fee
        fee_standard = 0.0005
        fee = []       

        # in case the BBS minuse handlign fee (0.15%) is still cheeper
        if self.price['BBS_win'] > self.trigger_threshold:
            self.trading_begin_time = int(time.time()*1000)+self.time_offset

            # because of the minimum quantity of the trading, calculate how much target Coin(symbol) can be selled completely with direct price
            self.cal_buy_volumn_symbol = self.buy_volumn/self.price['direct_sell']
            self.real_buy_volumn_symbol = (int(self.cal_buy_volumn_symbol/self.minQty[0]))*self.minQty[0]

            # caclulate how much between reference coin is needed based on real buying volumn
            self.cal_trading_volumn_between = self.real_buy_volumn_symbol*self.price['between_buy']
            # use round up integer to calculate the needed between reference coin volumn
            # in between buy case, some of the win will saved in between reference coin, but in between sell case, the between reference coin will be over selled
            self.real_trading_volumn_between = (math.ceil(self.cal_trading_volumn_between/self.minQty[2]))*self.minQty[2]

            # buy between refrence coin
            self.response_1 = BinanceRestLib.createMarketOrder(self.coin[1],self.coin[0],"BUY",self.real_trading_volumn_between,self.time_offset)
            fee.append(self.real_trading_volumn_between*fee_standard*self.price['rate_buy'])
            
            # buy target coin with between reference coin
            self.response_2 = BinanceRestLib.createMarketOrder(self.symbol,self.coin[1],"BUY",self.real_buy_volumn_symbol,self.time_offset)
            fee.append(self.real_buy_volumn_symbol*fee_standard*self.price['BBS_price'])

            # sell target coin with direct reference coin
            self.response_3 = BinanceRestLib.createMarketOrder(self.symbol,self.coin[0],"SELL",self.real_buy_volumn_symbol,self.time_offset)
            fee.append(self.real_buy_volumn_symbol*fee_standard*self.price['direct_sell'])

            self.trading_end_time = int(time.time()*1000)+self.time_offset
            
        # in case the BSS minuse handling fee (0.15%) is still cheeper
        if self.price['BSS_win'] > self.trigger_threshold:
            self.trading_begin_time = int(time.time()*1000)+self.time_offset

            # because of the minimum quantity of the trading, calculate how much target Coin(symbol) should be buy with triangle price
            self.cal_buy_volumn_symbol = self.buy_volumn/self.price['direct_buy']
            self.real_buy_volumn_symbol = (int(self.cal_buy_volumn_symbol/self.minQty[0]))*self.minQty[0]

            # caclulate how much between reference coin is needed based on real buying volumn
            self.cal_trading_volumn_between = self.real_buy_volumn_symbol*self.price['between_sell']
            # use round up integer to calculate the needed between reference coin volumn
            # in BBS buy case, some of the win will saved in between reference coin, but in BSS case, the between reference coin will be over selled
            self.real_trading_volumn_between = (math.ceil(self.cal_trading_volumn_between/self.minQty[2]))*self.minQty[2]

            # buy target coin with direct reference coin
            self.response_1 = BinanceRestLib.createMarketOrder(self.symbol,self.coin[0],"BUY",self.real_buy_volumn_symbol,self.time_offset)
            fee.append(self.real_buy_volumn_symbol*fee_standard*self.price['direct_buy'])

            # sell target coin with between reference coin
            self.response_2 = BinanceRestLib.createMarketOrder(self.symbol,self.coin[1],"SELL",self.real_buy_volumn_symbol,self.time_offset)
            fee.append(self.real_buy_volumn_symbol*fee_standard*self.price['BSS_price'])

            # sell between refrence coin
            self.response_3 = BinanceRestLib.createMarketOrder(self.coin[1],self.coin[0],"SELL",self.real_trading_volumn_between,self.time_offset)
            fee.append(self.real_trading_volumn_between*fee_standard*self.price['rate_sell'])
            
            self.trading_end_time = int(time.time()*1000)+self.time_offset

        print(self.price, " @", self.price_time)

        if self.price['BBS_win'] > self.trigger_threshold or self.price['BSS_win'] > self.trigger_threshold:
            return 1
        else:
            return 0

    # check whether with there is still win rate with the current sell price, if not create a limit order instead of direct sell
    def triangleTradingSell(self, price_thread):
        # synchro with the tread
        price_thread.join()
        # # update price
        # self.price['between_buy'] = price_thread.price['asks_vol']
        # self.price['between_sell'] = price_thread.price['bids_vol']

        # # Calculate BSS price and win
        # self.price['BSS_price'] = self.price['between_sell']*self.price['rate_sell'] 
        # self.price['BSS_win'] = self.price['BSS_price']/self.price['direct_buy']

        # if it has still win with market sell
        # if self.price['BSS_win'] > self.trigger_threshold:

        # Use between coin price tendence to decide, whether a limit sell is needed
        current_between_sell =  price_thread.price['bids_vol']
        # If the sell price is going up, sell the between coin directly with market price
        if current_between_sell>self.price['between_sell']:
            # sell target coin with between reference coin
            self.response_2 = BinanceRestLib.createMarketOrder(self.symbol,self.coin[1],"SELL",self.real_buy_volumn_symbol,self.time_offset)
            # fee.append(self.real_buy_volumn_symbol*fee_standard*self.price['BSS_price'])
       
        # else, create a limit sell order
        # in this case, the trading will be continued until the limit order is taken by others. Otherwise an exception with "not enough infuluence" will be return
        else:
            print("Special Case: create limit trading to sell the coins")
            # calculate a new sell limit price with aks_1(buy) price - 1
            self.price['between_sell'] = round(float(price_thread.price['asks_1'] - self.minPrice[1]),self.price_precise[1])
            # sell target coin with between reference coin
            self.response_2 = BinanceRestLib.createLimitOrder(self.symbol,self.coin[1],"SELL",self.real_buy_volumn_symbol,self.price['between_sell'],self.time_offset)
            # fee.append(self.real_buy_volumn_symbol*fee_standard*self.price['between_sell']*self.price['rate_sell'])

            # get the order id
            orderId = self.response_2['orderId']

            order_param = {}
            order_param['symbol'] = self.symbol + self.coin[1]
            order_param['orderId'] = orderId
            order_param['timestamp'] = int(time.time()*1000)+self.time_offset
            # check the order state
            self.limit_order = BinanceRestLib.getSignedService("order",order_param)
            # wait until the limit order is filled
            while True:
                time.sleep(1)
                print("Waiting limit sell for bewteen coin ...")
                order_param['timestamp'] = int(time.time()*1000)+self.time_offset
                self.limit_order = BinanceRestLib.getSignedService("order",order_param)
                if 'status' in self.limit_order:
                    if self.limit_order['status'] == "FILLED":
                        break
                else:
                    print("Unknown status:")
                    print(json.dumps(self.limit_order, indent=4))

            print(json.dumps(self.limit_order, indent=4))
            
        # sell between refrence coin
        self.response_3 = BinanceRestLib.createMarketOrder(self.coin[1],self.coin[0],"SELL",self.real_trading_volumn_between,self.time_offset)
        # fee.append(self.real_trading_volumn_between*fee_standard*self.price['rate_sell'])
        
        self.trading_end_time = int(time.time()*1000)+self.time_offset
    
    # the sell phase always with limit trading on between coin    
    def triangleTradingSellLimit(self):
        # get current between sell price
        thread2 = BinanceRestLib.getPriceThread(2, "Thread-2", self.symbol, self.coin[1], self.volumn[1])
        thread2.start()

        # sell between refrence coin with market price firstly
        self.response_3 = BinanceRestLib.createMarketOrder(self.coin[1],self.coin[0],"SELL",self.real_trading_volumn_between,self.time_offset)
        print(json.dumps(self.response_3, indent=4))

        thread2.join()
        
        # # create a current sell price based on current sell_1 price
        # current_between_sell = round(float(thread2.price['asks_1'] - self.minPrice[1]),self.price_precise[1])
        # # calculate minimum price to sell the between coin without loss
        # #TODO: need to get the real selling price from response3
        # minimum_between_sell = round((self.price['direct_buy']*1.0015/self.price['rate_sell']),self.price_precise[1])

        # print(self.price, " @", self.price_time)
        # print("Saved price: ", self.price['between_sell'])
        # print("Current sell price: ", current_between_sell)
        # print("Minimum sell price: ", minimum_between_sell)
        
        # # choose the bigger price betwen current sell price and minimum sell price as the executing selling price
        # if minimum_between_sell > current_between_sell:
        #     self.price['between_sell'] = minimum_between_sell
        # else:
        #     self.price['between_sell'] = current_between_sell

        # use a conservative trading price to garantee the continue tradings
        minimum_between_sell = round((self.price['direct_buy']*1.0021/self.price['rate_sell']),self.price_precise[1])
        self.price['between_sell'] = minimum_between_sell
        print("Saved price: ", self.price['between_sell'])
        print("Minimum sell price: ", minimum_between_sell)

        print("begin between sell")

        # create limit trading for between coin
        self.response_2 = BinanceRestLib.createLimitOrder(self.symbol,self.coin[1],"SELL",self.real_buy_volumn_symbol,self.price['between_sell'],self.time_offset)

        print(json.dumps(self.response_2, indent=4))

        # get the order id
        orderId = self.response_2['orderId']

        order_param = {}
        order_param['symbol'] = self.symbol + self.coin[1]
        order_param['orderId'] = orderId
        order_param['timestamp'] = int(time.time()*1000)+self.time_offset
        # check the order state
        self.limit_order = BinanceRestLib.getSignedService("order",order_param)
        # wait until the limit order is filled
        while True:
            time.sleep(1)
            # print("Waiting limit sell for bewteen coin ...")
            order_param['timestamp'] = int(time.time()*1000)+self.time_offset
            self.limit_order = BinanceRestLib.getSignedService("order",order_param)
            if 'status' in self.limit_order:
                if self.limit_order['status'] == "FILLED":
                    break
                # if the trading is cancelled manually, wait 5 min for the next rund
                if self.limit_order['status'] == "CANCELED":
                    print("Cancel the trading and sell the coin manually")
                    time.sleep(300)
                    break
            else:
                print("Unknown status:")
                print(json.dumps(self.limit_order, indent=4))

        print(json.dumps(self.limit_order, indent=4))
        
        self.trading_end_time = int(time.time()*1000)+self.time_offset

    # check open orders on ETHBTC to identify, whether a remote start is requested
    def isRemoteStart(self):
        # create parameters
        param = {}
        param['symbol'] = 'ETHBTC'
        param['recvWindow'] = 5000
        param['timestamp'] = int(time.time()*1000)+self.time_offset
        # get all open orders for this symbol
        result = BinanceRestLib.getSignedService("openOrders",param)
        print(json.dumps(result, indent=4))

        # if no remote start request, return directly
        if len(result) == 0:
            return False
        
        # get the last open order, which contains remote start info
        last_open = result[-1]
        orderId = last_open["orderId"]
        startInfo = str(last_open["price"])

        # check wether the  first position is 1 (it could be changed if ETHBTC rate is stark changed)
        if startInfo[0] != '1':
            return False
        
        # use 2 ~ 4 position to find the trading symbol
        symbol_index = int(startInfo[2:5])
        self.symbol = self.symbol_list[symbol_index]

        # use 5 ~ 8 position to find the trading times
        self.trading_times = int(startInfo[5:8])

        # cancle this trading, since it is only used to translate info
        cancel_result = BinanceRestLib.cancelOrder("ETH","BTC",orderId,self.time_offset)
        print(json.dumps(cancel_result, indent=4))

        return True

    def getSymbolList(self):
        symbol_file = open('TriangleSymbols2.txt','r')
        self.symbol_list = symbol_file.read().split(',')
        symbol_file.close()

    def updateTimeOffset(self):
        self.time_offset = BinanceRestLib.getServerTimeOffset()
        print("Update time offset to: ", self.time_offset)

    def runTriangleStrategy(self):
        begin_time = time.time()
        trading_index = 0

        while True:
            self.getTrianglePrice()
            result = self.triangleTradingLimitTwice()
            # if one trading is compelted
            if result == 1:
                print(trading_index, " trading is completed --------------------------------------")
                trading_index += 1
                # output trading into to console and save it into to file
                self.printLog()
                self.writeLog()
                # finish this trading group if the defined trading times is reached
                if trading_index > self.trading_times:
                    break

            # resnycho time offset in every 10min
            if time.time()-begin_time > 600:
                self.updateTimeOffset()
                begin_time = time.time()
                print("Resynchronise time offset with: ", self.time_offset)

            time.sleep(1)
        
        print("Trading mission with ", self.trading_times, " times trading is completed")

        # calculate balance
        coin_0_change = float(self.current_balance[self.coin[0]]) - float(self.begin_balance[self.coin[0]])
        coin_1_change = float(self.current_balance[self.coin[1]]) - float(self.begin_balance[self.coin[1]])
        coin_0_balance = coin_0_change + coin_1_change*self.price['rate_sell']
        win_rate = (coin_0_balance/0.0012) - (0.0015*self.trading_times)

        # create a info limit trading to notice the remote side, that the trading group is completed
        price = round(win_rate, 6) + 3
        response = BinanceRestLib.createLimitOrder("ETH","BTC","SELL",0.011,price,self.time_offset)
        print(response)
        
        # reset the begin balance
        self.begin_balance = self.current_balance

            

    def writeLog(self):
        file_out = open('TradingInfo.log','a')
        file_out.write(str(datetime.datetime.now())+'\n')
        file_out.write(str(self.price) + " @" + str(self.price_time) + '\n')

        file_out.write("Fill the triangle trading condition ----------------------------------")
        file_out.write("Calculated Buy Symbol: %f \n" %(self.cal_buy_volumn_symbol))
        file_out.write("Real Buy Symbol: %f \n" %(self.real_buy_volumn_symbol))
        file_out.write("Calculated Trading Between: %f \n"  %(self.cal_trading_volumn_between))
        file_out.write("Real Trading Between: %f \n" %(self.real_trading_volumn_between))

        file_out.write("Trading begin -------------------------------@ %f \n" %(self.trading_begin_time))
        file_out.write("Step 1:\n")
        json.dump(self.response_1, file_out)
        file_out.write("Step 2:\n")
        json.dump(self.response_2, file_out)
        file_out.write("Step 3:\n")
        json.dump(self.response_3, file_out)
        file_out.write("Trading end -------------------------------@ %f \n" %(self.trading_end_time))

        file_out.write("Calculated Balance:\n")
        if self.price['BBS_win'] > self.trigger_threshold:
            buy_volumn = self.real_trading_volumn_between*self.price['rate_buy']
            sell_volumn = self.real_buy_volumn_symbol*self.price['direct_sell']
            between_change = self.real_trading_volumn_between-self.cal_trading_volumn_between            
        if self.price['BSS_win'] > self.trigger_threshold:
            buy_volumn = self.real_buy_volumn_symbol*self.price['direct_buy']
            sell_volumn = self.real_trading_volumn_between*self.price['rate_sell']
            between_change = self.cal_trading_volumn_between-self.real_trading_volumn_between

        file_out.write("Buy volumn: %f \n" %(buy_volumn))
        file_out.write("Sell volumn: %f \n" %(sell_volumn))
        file_out.write("Between balence: %f \n" %(between_change))
        file_out.write("Win: %f \n" %(sell_volumn-buy_volumn+between_change*self.price['rate_sell']))

        file_out.write("Real Balance:\n")
        file_out.write("Before trading --------------------------------\n")
        json.dump(self.begin_balance, file_out)
        file_out.write("\nAfter trading --------------------------------\n")
        json.dump(self.current_balance, file_out)
        file_out.write("\n")

        # calculate balance change
        coin_0_change = float(self.current_balance[self.coin[0]]) - float(self.begin_balance[self.coin[0]])
        coin_1_change = float(self.current_balance[self.coin[1]]) - float(self.begin_balance[self.coin[1]])
        file_out.write("Coin %s change is: %f \n" %(self.coin[0], coin_0_change))
        file_out.write("Coin %s change is: %f \n" %(self.coin[1], coin_1_change))
        file_out.write("Win since beginning: %f \n" %(coin_0_change + coin_1_change*self.price['rate_sell']))

        # calculate balance change to the last trade
        coin_0_change = float(self.current_balance[self.coin[0]]) - float(self.last_balance[self.coin[0]])
        coin_1_change = float(self.current_balance[self.coin[1]]) - float(self.last_balance[self.coin[1]])
        file_out.write("Coin %s change is: %f \n" %(self.coin[0], coin_0_change))
        file_out.write("Coin %s change is: %f \n" %(self.coin[1], coin_1_change))
        file_out.write("Win since last trade: %f \n" %(coin_0_change + coin_1_change*self.price['rate_sell']))
        self.last_balance = self.current_balance

        file_out.close()

    def printLog(self):
        print(self.price, " @", self.price_time)

        print("Fill the triangle trading condition ----------------------------------")
        print("Calculated Buy Symbol: ", self.cal_buy_volumn_symbol)
        print("Real Buy Symbol: ", self.real_buy_volumn_symbol)
        print("Calculated Trading Between: ", self.cal_trading_volumn_between)
        print("Real Trading Between: ",self.real_trading_volumn_between)

        print("Trading begin -------------------------------@", self.trading_begin_time)
        print("Step 1:")
        print(json.dumps(self.response_1, indent=4))
        print("Step 2:")
        print(json.dumps(self.response_2, indent=4))
        print("Step 3:")
        print(json.dumps(self.response_3, indent=4))
        print("Trading end -------------------------------@", self.trading_end_time)

        print("Calculated Balance:")
        # in case BBS
        if self.price['BBS_win'] > self.trigger_threshold:
            buy_volumn = self.real_trading_volumn_between*self.price['rate_buy']
            sell_volumn = self.real_buy_volumn_symbol*self.price['direct_sell']
            between_change = self.real_trading_volumn_between-self.cal_trading_volumn_between          
        # in case BSS
        if self.price['BSS_win'] > self.trigger_threshold:
            buy_volumn = self.real_buy_volumn_symbol*self.price['direct_buy']
            sell_volumn = self.real_trading_volumn_between*self.price['rate_sell']
            between_change = self.cal_trading_volumn_between-self.real_trading_volumn_between

        print("Buy volumn: ", buy_volumn)
        print("Sell volumn: ", sell_volumn) 
        print("Between balence: ", between_change)
        print("Win: ", sell_volumn-buy_volumn+between_change*self.price['rate_sell'])

        print("Real Balance:")
        print("Before trading --------------------------------")
        print(self.begin_balance)
        print("After trading --------------------------------")
        self.current_balance = BinanceRestLib.getBalance(self.balance_coin_list, self.time_offset)
        print(self.current_balance)
        print()

        # calculate balance change to the beginning
        coin_0_change = float(self.current_balance[self.coin[0]]) - float(self.begin_balance[self.coin[0]])
        coin_1_change = float(self.current_balance[self.coin[1]]) - float(self.begin_balance[self.coin[1]])
        print("Coin %s change is: %f" %(self.coin[0], coin_0_change))
        print("Coin %s change is: %f" %(self.coin[1], coin_1_change))
        print("Win since beginning: ", coin_0_change + coin_1_change*self.price['rate_sell'])

        # calculate balance change to the last trade
        coin_0_change = float(self.current_balance[self.coin[0]]) - float(self.last_balance[self.coin[0]])
        coin_1_change = float(self.current_balance[self.coin[1]]) - float(self.last_balance[self.coin[1]])
        print("Coin %s change is: %f" %(self.coin[0], coin_0_change))
        print("Coin %s change is: %f" %(self.coin[1], coin_1_change))
        print("Win since last trade: ", coin_0_change + coin_1_change*self.price['rate_sell'])


def checkBestTarget():
    ref_coin = [['BTC', 'ETH'], ['ETH','BNB'], ['BTC','BNB']]

    symbol_file = open('C:/Users/Cibobo/Documents/Coins/Python/TriangleSymbols.txt','r')
    symbols = symbol_file.read().split(',')
    print(symbols)

    symbol_file.close()

    win_list_BSS = {}
    win_list_BBS = {}

    for symbol in symbols:
        trian = TriangleStrategy(symbol,ref_coin[1])
        
        print("Begin price check of ", symbol, int(time.time()*1000)+trian.time_offset)
        
        win_list_BSS[symbol] = 0
        win_list_BBS[symbol] = 0

        begin_time = time.time()
        while True:
            trian.getTrianglePrice()
            print(trian.price)

            if trian.price['BSS_win']>win_list_BSS[symbol]:
                win_list_BSS[symbol] = trian.price['BSS_win']
            if trian.price['BBS_win']>win_list_BBS[symbol]:
                win_list_BBS[symbol] = trian.price['BBS_win']
        
            if time.time()-begin_time > 10:
                break
            time.sleep(1)

    sort_BSS = sorted(win_list_BSS.items(), key=lambda win_list_BSS:win_list_BSS[1])
    sort_BBS = sorted(win_list_BBS.items(), key=lambda win_list_BBS:win_list_BBS[1])

    print(sort_BSS)
    print(sort_BBS)



