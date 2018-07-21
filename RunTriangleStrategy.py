import time
import datetime

import TriangleStrategy

# possible triangle trading combination
ref_coin = [['BTC', 'ETH'], ['ETH','BNB'], ['BTC','BNB']]

# target coin symbol
symbol = 'BNB'

def isLocalStart():
    result = False

    fileIn = open("Config.txt",'r')
    config = fileIn.readline()
    fileIn.close()

    fileOut = open("Config.txt",'w')
    fileOut.write("pause")
    fileOut.close()

    if config != "pause":
        result = True
    
    return result, config


begin_time = time.time()

tradInstance = TriangleStrategy.TriangleStrategy(symbol,ref_coin[0]) 
print("Begin Triangle Trading @", int(time.time()*1000)+tradInstance.time_offset)

while True:
    # isStart = tradInstance.isRemoteStart()
    # isStart = True

    isStart, config = isLocalStart()

    if isStart:
        inputs = config.split(",")
        tradInstance.symbol = str(inputs[0])
        tradInstance.trading_times = int(inputs[1])
        print("Begin triangle trading with %s for %i times" %(tradInstance.symbol, tradInstance.trading_times))        
        tradInstance.runTriangleStrategy()
    else:
        print("Waiting for the remote control")

    # resnycho time offset in every 10min
    if time.time()-begin_time > 600:
        tradInstance.updateTimeOffset()
        begin_time = time.time()
        print("Resynchronise time offset with: ", tradInstance.time_offset, " @ ", datetime.datetime.now())
        # break
    time.sleep(20)

tradInstance.printLog()
tradInstance.writeLog()
print("end")

