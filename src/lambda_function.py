import json
from requests_oauthlib import OAuth1Session
import boto3
import requests
import urllib.parse
from io import BytesIO
import time

SCRAPBOX_API_ROOT = 'https://scrapbox.io/api'
TWITTER_API_V2_ROOT = 'https://api.twitter.com/2'
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
    media_ids = fetchData()

    for media_id in media_ids:
        tweet(text, [media_id])

        print('tweet complete.')
        print(f'text: {text}')
        print(f'media_id: {media_id}')

def handle_error(res):
    try:
        res.raise_for_status()
    except requests.HTTPError as e:
        print(res.json())
        raise e
    return res

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
            if (page['pin'] == 0 and page['image']):
                pages.append(page)

        cnt = len(json['pages'])

        print(f'{cnt} of {json["count"]} pages fetched from Scrapbox.')

        skip += cnt
        if (cnt < 100):
            break

    # 画像を取得する
    images = []
    for page in pages:
        res = requests.get(page['image'])
        images.append(handle_error(res).content)

        print(f'{page["image"]} fetched.')
    
    print('Fetch images from Scrapbox complete.')

    # Twitterに画像をアップロードし、メディアIDを取得する
    media_ids = []
    for image in images:
        media_ids.append(upload_to_twitter(image))

    print('Upload images to Twitter complete.')

    return media_ids

def upload_to_twitter(image):
    # ファイルを分割してアップロードする
    url = f'{TWITTER_MEDIA_API_ROOT}/upload.json'
    total_bytes = len(image)

    print('INIT')

    res = oauth.post(url=url, data={
        'command': 'INIT',
        'total_bytes': total_bytes,
        'media_type': 'image/png',
    })
    media_id = handle_error(res).json()['media_id']
    print(f'Media ID: {media_id}')

    print('APPEND')

    segment_id = 0
    bytes_sent = 0
    file = BytesIO(image)

    while (bytes_sent < total_bytes):
        res = oauth.post(url=url,
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

        print(f'{bytes_sent} of {total_bytes} bytes uploaded.')

    print('Upload chunks complete.')

    print('FINALIZE')

    res = oauth.post(url=url, data={
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

    print(f'Media processing status is {state}.')

    if (state == 'succeeded'):
        return
    if (state == 'failed'):
        raise Exception('Failed to upload image to Twitter.')

    check_after_secs = processing_info['check_after_secs']
    
    print(f'Checking after {check_after_secs} seconds')
    time.sleep(check_after_secs)
    
    print('STATUS')

    res = oauth.get(url=url, data={
        'command': 'STATUS',
        'media_id': media_id
    })
    processing_info = handle_error(res).json().get('processing_info', None)
    check_status(processing_info, url, media_id)

def tweet(text, media_ids = []):
    res = oauth.post(
        f'{TWITTER_API_V2_ROOT}/tweets',
        data={
            'text': text,
            'media': {
                'media_ids': media_ids,
            },
        }
    )
    handle_error(res)