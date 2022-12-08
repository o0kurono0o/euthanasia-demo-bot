import json
from requests_oauthlib import OAuth1Session
import boto3
import requests
import urllib.parse

SCRAPBOX_API_ROOT = 'https://scrapbox.io/api'

ssm_client = boto3.client('ssm')

oauth = None

def init():
    res = ssm_client.get_parameter(
        Name='/credentials/twitter/kuronoSub/euthanasia-demo-bot',
        WithDecryption=True
    )
    params = json.loads(res['Parameter']['Value'])
    
    api_key = params['api_key']
    api_key_secret = params['api_key_secret']
    access_token = params['access_token']
    access_token_secret = params['access_token_secret']

    global oauth
    oauth = OAuth1Session(
        api_key,
        api_key_secret,
        access_token,
        access_token_secret
    )

init()

def lambda_handler(event, context):
    text = '#国は安楽死を認めてください'
    tweet(text)

def handle_error(res):
    status = res.status_code
    if (200 <= status < 400):
        return res
    else:
        res.raise_for_status()

def fetchData():
    # 安楽死コラージュのページ一覧を取得する
    pages = []
    skip = 0

    while (True):
        params = urllib.parse.urlencode({
            'sort': 'created',
            'skip': skip,
        })
        
        res = requests.get(
            url=f'{SCRAPBOX_API_ROOT}/pages/euthanasia-collage?{params}'
        )
        json = handle_error(res).json()
        for page in json['pages']:
            if (page.pin == 0):
                pages.append(page)

        skip += len(json['pages'])
        if (len(json['pages']) < 100):
            break

    # 画像をダウンロードする
    images = []
    for page in pages:
        res = requests.get(page.image)
        images.append(handle_error(res).content)

def tweet(text):
    payload = {'text': text}
    res = oauth.post(
        'https://api.twitter.com/2/tweets',
        json=payload
    )
    if res.status_code != 201:
        raise Exception(
            '[Error] {} {}'.format(res.status_code, res.text)
        )