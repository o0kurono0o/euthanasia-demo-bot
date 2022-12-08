import json
from requests_oauthlib import OAuth1Session
import boto3
import requests
import urllib.parse
from io import BytesIO
import time

SCRAPBOX_API_ROOT = 'https://scrapbox.io/api'
TWITTER_MEDIA_API_ROOT = 'https://upload.twitter.com/1.1/media'

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

    # Twitterに画像をアップロードし、メディアIDを取得する
    media_ids = []
    for image in images:
        media_ids.append(upload_to_twitter(image))

def upload_to_twitter(image):
    # ファイルを分割してアップロードする
    url = f'{TWITTER_MEDIA_API_ROOT}/upload.json'
    total_byte = len(image)

    res = requests.post(url=url, data = {
        'command': 'INIT',
        'total_byte': total_byte,
        'media_type': 'image/png',
    })
    media_id = handle_error(res).json()['media_id']
    print(f'Media ID: {media_id}')

    segment_id = 0
    bytes_sent = 0
    file = BytesIO(image)

    while (bytes_sent < total_byte):
        res = requests.post(url=url,
            data={
            'command': 'APPEND',
            'media_id': media_id,
            'segment_index': segment_id,
            },
            files={
                'media': file.read(4*1024*1024),
            }
        )
        handle_error(res)

        segment_id += 1
        bytes_sent = file.tell()
    print('Upload chunks complete.')

    res = requests.post(url=url, data={
        'command': 'FINALIZE',
        'media_id': media_id,
    })

    check_status(
        handle_error(res).json().get('processing_info', None),
        url,
        media_id
    )

    return media_id

def check_status(processing_info, url, media_id):
    if (processing_info is None):
        return
    
    state = processing_info['state']
    if (state == 'succeeded'):
        return
    if (state == 'failed'):
        raise Exception('Failed to upload image to Twitter.')

    check_after_secs = processing_info['check_after_secs']
    
    print(f'Checking after {check_after_secs} seconds')
    time.sleep(check_after_secs)
    
    res = requests.get(url=url, data={
        'command': 'STATUS',
        'media_id': media_id
    })
    processing_info = handle_error(res).json().get('processing_info', None)
    check_status(processing_info, url, media_id)

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