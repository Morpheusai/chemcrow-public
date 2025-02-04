import aiohttp  
import asyncio  
import json  

async def test_post():  
    headers = {'Content-Type': 'application/json'}  
    data = {"message": "七夕情人节快乐！"}  
    sseresp = aiohttp.request("POST", r"http://127.0.0.1:18080/sse", headers=headers, data=json.dumps(data))  
    async with sseresp as r:  
        async for chunk in r.content.iter_any():  
            print(chunk.decode())  

if __name__ == '__main__':  
    loop = asyncio.get_event_loop()  
    loop.run_until_complete(test_post())
