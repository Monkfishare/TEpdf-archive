import asyncio,aiohttp,platform
import pandas as pd

class Downloader:

    def __init__(self, url_list, 
                        type='get', 
                        headers='', 
                        data='', 
                        proxy='',
                        tSleep=1,
                        nCache=500,
                        outFilename='out.pkl'):
        self.url_list = url_list
        self.headers = headers
        self.data = data
        self.proxy = proxy
        self.type = type
        self.tSleep = tSleep
        self.nCache = nCache
        self.outFilename = outFilename
    
    async def get(self, url):
        try:
            async with self.sem:
                async with aiohttp.ClientSession(headers=self.headers) as session:
                    async with session.get(url=url, headers=self.headers, proxy=self.proxy) as response:
                        res = await response.read()
                        await asyncio.sleep(self.tSleep)
        except:
            res = b'NULL from response'
        
        return pd.DataFrame(data={'url':url, 'response': res},index=[0])

    async def post(self, url):
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(url=url, headers=self.headers, data=self.data) as response:
                    res = await response.read()
        except:
            res = b'NULL from response'
        
        return pd.DataFrame(data={'url':url, 'response': res},index=[0])
    
    async def tasker(self, njob):
        self.sem = asyncio.Semaphore(njob)
        df = pd.DataFrame()
        for idx in list(range(len(self.url_list)))[::self.nCache]:
            task_list = [self.get(url) for url in self.url_list[idx:idx+self.nCache]]
            L = await asyncio.gather(*task_list)
            df = pd.concat([df] + L, ignore_index=True)
            df.to_pickle(self.outFilename)
            print(f'Fetching {(idx+1)*self.nCache} entries')
        return df
    

    def run(self, njob=10):
        if platform.system() == 'Windows':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        df = asyncio.run(self.tasker(njob))
        return df


def fetchNullUrl(df):
    url_null = list(df.loc[df.response == b'NULL from response'].url)
    url_null += list(df.loc[df.response.map(lambda x: x.find(b'Just a moment')) > 0].url)
    return url_null

def retry(dfFilename, proxy, logging, nRetry=3):
    df = pd.read_pickle(dfFilename)
    for n in range(nRetry):
        url_null = fetchNullUrl(df)
        if len(url_null) > 0:
            logging.info(f'retry {n}: {dfFilename} {len(url_null)} null responses')
            print(f'retry {n}: {dfFilename} {len(url_null)} null responses')
            df_retry = Downloader(url_null,proxy=proxy, tSleep=5, outFilename='retry.pkl').run()
            df = pd.concat([df_retry, df],ignore_index=True).drop_duplicates(subset='url',keep='first')
            df.to_pickle(dfFilename)
        else:
            break
    return df

