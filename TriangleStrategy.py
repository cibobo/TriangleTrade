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
    minNotional = 0.01

    # standard volumn used for triangle strategy
    buy_volumn = minNotional * 1.5

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
        self.saveAccountInfo()

        # get needed Exchange Info
        self.getExchangeInfo()
        print(self.minQty)
        print(self.minPrice)

        # Use traiding minQty to ask first price, so that the requried buy/sell volumn can be estimated
        self.volumn = []
        for i in range(3):
            self.volumn.append({'buy':self.minQty[i],'sell':self.minQty[i]})
    
    def getExchangeInfo(self):
        exchangeInfo = BinanceRestLib.getExchangeInfo()

        self.minQty = []
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
        file_out = open('C:/Users/Cibobo/Documents/Coins/Python/AccountInfo.log','a')
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

        self.price['rate_buy'] = thread3.price['asks_vol']
        self.price['rate_sell'] = thread3.price['bids_vol']

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
        # self.price['direct_buy'] = (int((self.price['direct_sell'] + minPrice)/minPrice))*minPrice
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
        # update price
        self.price['between_buy'] = price_thread.price['asks_vol']
        self.price['between_sell'] = price_thread.price['bids_vol']

        # Calculate BSS price and win
        self.price['BSS_price'] = self.price['between_sell']*self.price['rate_sell'] 
        self.price['BSS_win'] = self.price['BSS_price']/self.price['direct_buy']

        # if it has still win with market sell
        if self.price['BSS_win'] > self.trigger_threshold:
            # sell target coin with between reference coin
            self.response_2 = BinanceRestLib.createMarketOrder(self.symbol,self.coin[1],"SELL",self.real_buy_volumn_symbol,self.time_offset)
            # fee.append(self.real_buy_volumn_symbol*fee_standard*self.price['BSS_price'])

            # sell between refrence coin
            self.response_3 = BinanceRestLib.createMarketOrder(self.coin[1],self.coin[0],"SELL",self.real_trading_volumn_between,self.time_offset)
            # fee.append(self.real_trading_volumn_between*fee_standard*self.price['rate_sell'])
            
            self.trading_end_time = int(time.time()*1000)+self.time_offset
        # else, create a limit sell order
        # in this case, the trading will be continued until the limit order is taken by others. Otherwise an exception with "not enough infuluence" will be return
        else:
            print("Special Case: create limit trading to sell the coins")
            # calculate a new sell limit price with aks_1(buy) price - 1
            self.price['between_sell'] = round(float(price_thread.price['asks_1'] - self.minPrice[1]),self.price_precise[1])
            # sell target coin with between reference coin
            self.response_2 = BinanceRestLib.createLimitOrder(self.symbol,self.coin[1],"SELL",self.real_buy_volumn_symbol,self.price['between_sell'],self.time_offset)
            # fee.append(self.real_buy_volumn_symbol*fee_standard*self.price['between_sell']*self.price['rate_sell'])

        print(json.dumps(self.limit_order, indent=4))

    def writeLog(self):
        self.file_out = open('C:/Users/Cibobo/Documents/Coins/Python/balance.txt','w+')
        self.file_out.write(self.price, " @", self.price_time)

        self.file_out.write("Fill the triangle trading condition ----------------------------------")
        self.file_out.write("Calculated Buy Symbol: ", self.cal_buy_volumn_symbol)
        self.file_out.write("Real Buy Symbol: ", self.real_buy_volumn_symbol)
        self.file_out.write("Calculated Trading Between: ", self.cal_trading_volumn_between)
        self.file_out.write("Real Trading Between: ",self.real_trading_volumn_between)

        self.file_out.write("Trading begin -------------------------------@", self.trading_begin_time)
        self.file_out.write("Step 1:")
        json.dump(self.response_1, self.file_out)
        self.file_out.write("Step 2:")
        json.dump(self.response_2, self.file_out)
        self.file_out.write("Step 3:")
        json.dump(self.response_3, self.file_out)
        self.file_out.write("Trading end -------------------------------@", self.trading_end_time)

        self.file_out.write("Calculated Balance:")
        if self.price['trig_win'] < 0.995:
            buy_volumn = self.real_trading_volumn_between*self.price['rate']
            sell_volumn = self.real_buy_volumn_symbol*self.price['direct_price']
            between_change = self.real_trading_volumn_between-self.cal_trading_volumn_between          
        else:
            buy_volumn = self.real_buy_volumn_symbol*self.price['direct_price']
            sell_volumn = self.real_trading_volumn_between*self.price['rate']
            between_change = self.cal_trading_volumn_between-self.real_trading_volumn_between

        self.file_out.write("Buy volumn: ", buy_volumn)
        self.file_out.write("Sell volumn: ", sell_volumn) 
        self.file_out.write("Between balence: ", between_change)
        self.file_out.write("Win: ", sell_volumn-buy_volumn+between_change*self.price['rate'])

        self.file_out.write("Real Balance:")
        self.file_out.write("Before trading --------------------------------")
        self.file_out.write(self.begin_balance)
        self.file_out.write("After trading --------------------------------")
        current_balance = BinanceRestLib.getBalance(self.balance_coin_list,self.time_offset)
        self.file_out.write(current_balance)
        self.file_out.write()

        # calculate balance change
        coin_0_change = current_balance[self.coin[0]] - self.begin_balance[self.coin[0]]
        coin_1_change = current_balance[self.coin[1]] - self.begin_balance[self.coin[1]]
        self.file_out.write("Coin %s change is: %f" %(self.coin[0], coin_0_change))
        self.file_out.write("Coin %s change is: %f" %(self.coin[1], coin_1_change))
        self.file_out.write("Win: ", coin_0_change + coin_1_change*self.price['rate'])

        self.file_out.close()

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
        current_balance = BinanceRestLib.getBalance(self.balance_coin_list, self.time_offset)
        print(current_balance)
        print()

        # calculate balance change
        coin_0_change = float(current_balance[self.coin[0]]) - float(self.begin_balance[self.coin[0]])
        coin_1_change = float(current_balance[self.coin[1]]) - float(self.begin_balance[self.coin[1]])
        print("Coin %s change is: %f" %(self.coin[0], coin_0_change))
        print("Coin %s change is: %f" %(self.coin[1], coin_1_change))
        print("Win: ", coin_0_change + coin_1_change*self.price['rate_sell'])


def checkBestTarget():
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


# possible triangle trading combination
ref_coin = [['BTC', 'ETH'], ['ETH','BNB'], ['BTC','BNB']]

# target coin symbol
symbol = 'NEO'

begin_time = time.time()
trading_index = 0

test = TriangleStrategy(symbol,ref_coin[1]) 
print("Begin Triangle Trading @", int(time.time()*1000)+test.time_offset)

while True:
    test.getTrianglePrice()
    # result = test.triangleTrading()  
    result = test.triangleTradingLimit()
    if result == 1:
        trading_index += 1
        print(trading_index, " trading is completed --------------------------------------")
        test.printLog()
        if trading_index > 2: 
            break
    #     test.printLog()
    # print(test.price)
    # if test.price['BSS_win']>1.002 or test.price['BBS_win']>1.002:
    #     print(test.price)
    #     print("Bingo!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    #     break
    # resnycho time offset in every 10min
    if time.time()-begin_time > 600:
        test.time_offset = BinanceRestLib.getServerTimeOffset()
        begin_time = time.time()
        print("Resynchronise time offset with: ", test.time_offset)
        # break
    time.sleep(1)

test.printLog()
print("end")