# cumulative LOB monitor

Little project which helps to monitor cumulative Limit Order Book (LOB) of BTC-PERPETUAL at Deribit.

- monitor_lob.py:
  - subscribes to limit order snapshots, updates, deletes, 
  - processes into cumulative LOB. 
  - sends cumulative LOB info to monitor via ws channel 
- monitor_lob.html is browser monitor equipped with javascript:
  - receives LOB data, 
  - fits it to exponenta and 
  - displaying it. 
  - "Demo mode" button uses LOB-simulator instead of Deribit feed. 

It was scaffolded with help of Claude.ai and then iterated/tuned to make it work. 

Run:
- python monitor_lob.py # feeds from Deribit, broadcast to localhost:8765 (you can change that)
- click on monitor_lob.html. push 'Connect' button. It will start listening broadcast on localhost:8765 channel and visualise. I checked Chrome, it works. 'Demo' button is just for historical reason.

Requires:
- python: websockets, asyncio. basically you will 
- html: none
