# My Project

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