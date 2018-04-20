import time

import TriangleStrategy

# possible triangle trading combination
ref_coin = [['BTC', 'ETH'], ['ETH','BNB'], ['BTC','BNB']]

# target coin symbol
symbol = 'XRP'

begin_time = time.time()

tradInstance = TriangleStrategy.TriangleStrategy(symbol,ref_coin[0]) 
print("Begin Triangle Trading @", int(time.time()*1000)+tradInstance.time_offset)

while True:
    isStart = tradInstance.isRemoteStart()

    if isStart:
        print("Begin triangle trading")
        tradInstance.runTriangleStrategy()
    else:
        print("Waiting for the remote control")

    # resnycho time offset in every 10min
    if time.time()-begin_time > 600:
        tradInstance.updateTimeOffset()
        begin_time = time.time()
        print("Resynchronise time offset with: ", tradInstance.time_offset)
        # break
    time.sleep(20)

tradInstance.printLog()
tradInstance.writeLog()
print("end")

