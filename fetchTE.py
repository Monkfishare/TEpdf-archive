from downloader import Downloader, retry
from bs4 import BeautifulSoup
import pandas as pd
import os, requests, re, logging, glob, platform, time
import urllib.request

js = """
    <script>
    window.tedl = window.tedl || {};
    // Resize iframes on articles with interactives when they send a RESIZE message
    window.addEventListener('message', (event) => {
    if (event.data.type === 'RESIZE') {
    Array.prototype.forEach.call(document.getElementsByTagName('iframe'), function (element) {
    if (element.contentWindow === event.source) {
    const height = parseInt(event.data.payload.height, 10);
    const elementHeight = parseInt(element.style.height, 10);
    if (isNaN(elementHeight) | Math.abs(elementHeight - height) > 10){
        element.style.height = height + 'px';
    }
    // 
    console.log(elementHeight - height);
    }
    });
    }
    }, false);
    </script>
    """

def fetchSection(cl,docu):
    link_list = []
    for i in docu.findAll(class_=cl):
        if i.find('a'):
            link = i.find('a').attrs['href']
            if ('https' not in link) and ('/html/' not in link):
                link = "https://www.economist.com" + link
                # replace as local links in the index page
                i.find('a').attrs['href'] = './html/'+link.split('/')[-1].replace('?','') +'.html'
        link_list.append(link)
    return link_list

def fetchArticleLink(indexResponse):    
    doc = BeautifulSoup(indexResponse, features="lxml")
    docu = doc.find(class_='layout-weekly-edition')
    link_list = []
    section_list = ['weekly-edition-wtw__item',
                    'teaser-weekly-edition--leaders',
                    'teaser-weekly-edition--briefing',
                    'teaser-weekly-edition--headline-only',
                    'teaser-weekly-edition--cols']
    for section in section_list:
        link_list = link_list + fetchSection(section, docu)

    return link_list

def fetchSecondArticleLink(articleResponse):
    link_list = []
    doc = BeautifulSoup(articleResponse, features="lxml")
    if doc.find(class_="article__body-text"):
        if doc.find(class_="article__body-text article__body-text--dropcap"):
            body = doc.find(class_="article__body-text article__body-text--dropcap").parent
        else:
            body = doc.find(class_="article__body-text").parent
        
        for i in body.findAll('a',{'href':re.compile("^/")}):
            url = i.attrs['href']
            if 'https' not in url:
                url = 'https://www.economist.com' + url
            if (len(url.split('/')) > 4) & ('newsletter' not in url) & ('podcast' not in url) & ('/1843/' not in url) & ('email' not in url):
                link_list.append(url)
    return link_list

    
def fetchFigureUrl(figure):
    figurl = []
    fig = figure.find('img')
    if fig:
        if figure.find('meta'):
            figurl = [figure.find('meta').attrs['content']]
        else:
            figurl = [fig.attrs['src']]
        if 'https' not in figurl[0]:
            figurl = ['https://www.economist.com' + figurl[0]]
    return figurl

def selectBody(doc):
    if doc.find(class_="article__body-text"):
        if doc.find(class_="article__body-text article__body-text--dropcap"):
            body = doc.find(class_="article__body-text article__body-text--dropcap").parent
        else:
            body = doc.find(class_="article__body-text").parent
    elif doc.find('section',{'data-body-id':'cp1'}):
        body = doc.find('section',{'data-body-id':'cp1'})
    elif doc.find('section',{'data-body-id':'cp2'}):
        body = doc.find('section',{'data-body-id':'cp2'})
    elif doc.find(class_='article-text'):
        body = doc.find(class_='article-text').parent
        if body.find(class_='related-content'):
            body.find(class_='related-content').decompose()
    else:
        body = ''

    return body

def fetchImageLink(articleResponse):
    doc = BeautifulSoup(articleResponse, features="lxml")
    if doc.find('figure'):
        link_list = fetchFigureUrl(doc.find('figure'))
    body = selectBody(doc)
    if body != '':
        for figure in body.findAll("figure"):
            link_list += fetchFigureUrl(figure)
    return link_list

def fetchAI(url):
    r = requests.get(url)
    doc = BeautifulSoup(r.content,features="lxml")
    
    if 'acast' in url:
        return
    if doc.find('title'):
        if 'audio-player' in doc.find('title').text:
            return
    
    # download background images in graphic-details
    for i in doc.findAll("img"):
        if i.has_attr('data-src'):
            imgurl = i.attrs['data-src']
        else:
            imgurl = i.attrs['src']
        if imgurl[:2] == '//':
            imgurl = 'https:'+imgurl
        if '//' not in imgurl:
            imgurl = '/'.join(url.split('/')[:-1]) + '/' + imgurl
        if 'ad' in imgurl:
            continue
        if 'svg+xml' in imgurl:
            continue
        img = requests.get(imgurl).content
        imgfile = './image/'+imgurl.split('/')[-1]
        with open(imgfile,"wb") as f:
            f.write(img)
        i.attrs['src'] = '../image/'+imgurl.split('/')[-1]
        i.attrs['data-src'] = '../image/'+imgurl.split('/')[-1]
        
    # save css file specific for graphic-details
    for css in doc.findAll(rel="stylesheet"):
        cssURL = css.attrs['href']
        if 'player' in cssURL:
            cssURL = 'https://www.youtube.com'+cssURL
        if 'http' not in cssURL:
            cssURL = '/'.join(url.split('?')[0].split('/')[:-1]) + '/' + cssURL
        csstext = requests.get(cssURL).text
        cssfile = './assets/'+cssURL.split('/')[-2]+'.css'
        with open(cssfile,'w',encoding='utf8') as f:
            f.write(csstext)
        css.attrs['href'] = '../assets/'+cssURL.split('/')[-2]+'.css'
    
    # save js file 
    for script in doc.findAll('script'):
        if script.has_attr('src'):
            scriptURL = script.attrs['src']
            if 'player' in scriptURL:
                scriptURL = 'https://www.youtube.com'+scriptURL
            if 'http' not in scriptURL:
                scriptURL = '/'.join(url.split('?')[0].split('/')[:-1]) + '/' +scriptURL
            scriptURL = scriptURL.split('?')[0]
            scripttext = requests.get(scriptURL).text
            scriptfile = './assets/'+scriptURL.split('/')[-1]
            with open(scriptfile,'w',encoding='utf8') as f:
                f.write(scripttext)
            script.attrs['src'] = '../assets/'+scriptURL.split('/')[-1]

    # save as separate html file
    file = './html/'+url.split('/')[-2].replace('?','') + '_index.html'
    with open(file,'w',encoding='utf8') as f:
        f.write(str(doc.html))

    return './'+url.split('/')[-2].replace('?','') + '_index.html'

def fetchEdition(editionUrl, proxy, logging, nRetry=3):

    indexFilename = editionUrl.split('/')[-1] + '_index.pkl'
    if not os.path.exists(indexFilename):
        print(f'Downloading {indexFilename}')
        df_index = Downloader([editionUrl],proxy=proxy,outFilename=indexFilename).run()
    df_index = retry(indexFilename, proxy, logging, nRetry)
    print(f'{indexFilename} loaded')

    article_link  = fetchArticleLink(df_index.loc[0,'response'])
    articleFilename = editionUrl.split('/')[-1] + '_articles.pkl'
    if not os.path.exists(articleFilename):
        print(f'Downloading {articleFilename}')
        df_article = Downloader(article_link, proxy=proxy, outFilename=articleFilename).run()
    df_article = retry(articleFilename, proxy, nRetry)
    print(f'{articleFilename} loaded')

    image_link = []
    imageFilename = editionUrl.split('/')[-1] + '_images.pkl'
    if not os.path.exists(imageFilename):
        for response in df_article.response:
            image_link += fetchImageLink(response)
        print(f'Downloading {imageFilename}')
        Downloader(image_link,proxy=proxy,tSleep=5,outFilename=imageFilename).run()
    df_image = retry(imageFilename, proxy, logging, nRetry)
    print(f'{imageFilename} loaded')

def genPrint():
    with open('index.html','r', encoding='utf8') as f:
        doc_index = BeautifulSoup(f.read(),features='lxml')

    cover_content = doc_index.find(class_='layout-weekly-edition-header').__copy__()

    body  = ''
    for i in doc_index.findAll('a'):
        link = i.attrs['href']
        if os.path.exists(link):
            with open(link,'r',encoding='utf') as f:
                # doc = formatAI(BeautifulSoup(f.read()))
                doc = BeautifulSoup(f.read(),features='lxml')
                body_part = doc.find('body')
                if body_part.find(class_="css-m3y5rp"):
                     body_part.find(class_="css-m3y5rp").decompose()
                if body_part.find('i'):
                    for info in body_part.findAll('i'):
                        info.decompose()     
                body += str(body_part) + '<br><div class="pagebreak"></div>'

    doc_index.find(class_='layout-weekly-edition').decompose()
    cover_html = str(doc_index).replace('</html>','') .replace('</body>','').replace("init1.css","../init.css").replace('./image','../image')
    cover_html += str(cover_content) + '</body><div class="pagebreak"> </div>'
    cover_html += str(body) + js + '</html>'

    with open('html/concat.html','w',encoding='utf8') as f:
        f.write(cover_html)

def genIndex(indexFilename):
    df_index = pd.read_pickle(indexFilename)
    doc = BeautifulSoup(df_index.loc[0,'response'], features="lxml")
    docu = doc.find(class_='layout-weekly-edition')

    # cover image
    headerImgURL = docu.find(class_='css-qts40t e1197rjj0').find('img').attrs['src']
    img = requests.get(headerImgURL).content
    with open('./image/cover.png',"wb") as f:
        f.write(img)
    for i in docu.findAll("img"):
        i.decompose()

    # replace article links as local links
    section_list = ['weekly-edition-wtw__item',
                    'teaser-weekly-edition--leaders',
                    'teaser-weekly-edition--briefing',
                    'teaser-weekly-edition--headline-only',
                    'teaser-weekly-edition--cols']
    for section in section_list:
        fetchSection(section, docu)

    html = '<html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1" /><head><link rel="stylesheet" href="init1.css"><title>The Economist</title></head><body><img src="./image/cover.png">'+str(docu)+'</body></html>'
    with open('index.html','w',encoding='utf8') as f:
        f.write(html)

def genImage(imageFilename):
    df_image = pd.read_pickle(imageFilename)
    for idx in df_image.index:
        url, response = df_image.loc[idx]
        imgfile = './image/'+url.split('/')[-1]
        with open(imgfile, 'wb') as f:
            f.write(response)

def genArticle(link, articleResponse='', downloadImage=False):

    if articleResponse == '':
        articleResponse = requests.get(link).content

    htmlname = './html/'+link.split('/')[-1].replace('?','')+'.html'
    doc = BeautifulSoup(articleResponse, features="lxml")

    if doc.find('iframe'):
        for frame in doc.findAll('iframe'):
            url = frame.attrs['src']
            if ('youtube' not in url) and ('acast' not in url):
                if 'https' not in url:
                    url = 'https://www.economist.com/' + url
                frame.attrs['src'] = fetchAI(url)

    body = selectBody(doc)
    if body == '':
        logging.warning(f'   x {link}')
        return
  
    # format article images
    fig_html = ''
    if doc.find('figure'):
        url = fetchFigureUrl(doc.find('figure'))
        if url and ('interactive/' not in link) and ('economic-and-financial-indicators/' not in link) and ('this-weeks-cover' not in link):
            src = url[0].split('/')[-1]
            fig_html = '<img id="myImg" src="../image/{}" width="auto" height="200">'.format(src)
    for figure in body.findAll("figure"):
        fig = figure.find('img')
        if fig:
            url = fetchFigureUrl(figure)[0]
            fig.attrs['src'] = '../image/'+url.split('/')[-1]
            fig.attrs['srcset'] = '../image/'+url.split('/')[-1]
            if downloadImage:
                with open(fig.attrs['src'],'wb') as f:
                    f.write(requests.get(url).content)

    for i in doc.findAll('style'):
        i.decompose()
    header = doc.find('section')

    html = '<html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1" /><head><link rel="stylesheet" href="../init.css"></head><body>'+str(header)+fig_html+str(body)+'</body>'+js+'</html>'
    
    with open(htmlname,'w',encoding='utf8') as f:
        f.write(html)

    return


if __name__ == "__main__":

    editionUrl = f'https://www.economist.com/weeklyedition'

    # proxy
    if platform.system() == 'Windows':
        proxy='http://127.0.0.1:7890'
    elif platform.system() == 'Linux':
        proxy=''

    # logging
    if os.path.exists('te.log'):
        os.remove('te.log')
    logging.basicConfig(filename='te.log', level=logging.INFO)

    # fetching
    edition = editionUrl.split('/')[-1]
    os.environ['https_proxy'] = proxy
    fetchEdition(editionUrl, proxy, logging)

    # generate HTMLs
    genIndex(f'{edition}_index.pkl')
    genImage(f'{edition}_images.pkl')
    df_article = pd.read_pickle(f'{edition}_articles.pkl')
    for idx in df_article.index:
        link, response = df_article.loc[idx]
        genArticle(link, response)
    genPrint()
