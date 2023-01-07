import json
from requests_oauthlib import OAuth1Session
import boto3
import requests
import urllib.parse
from io import BytesIO
import time

class App:
  SSM_PARAM_NAME = '/credentials/twitter/kuronoSub/euthanasia-demo-bot'
  SCRAPBOX_API_ROOT = 'https://scrapbox.io/api'
  SCRAPBOX_PROJECT_NAME = 'euthanasia-collage'
  TWITTER_API_V2_ROOT = 'https://api.twitter.com/2'
  TWITTER_MEDIA_API_ROOT = 'https://upload.twitter.com/1.1/media'
  TWEET_HASHTAG = '#国は安楽死を認めてください'

  def __init__(self):
    self.ssm_client = boto3.client('ssm')
    self.oauth = None
    self.media_ids = []

  def init(self):
    res = self.ssm_client.get_parameter(
        Name=App.SSM_PARAM_NAME,
        WithDecryption=True
    )
    params = json.loads(res['Parameter']['Value'])

    self.oauth = OAuth1Session(
        client_key=params['api_key'],
        client_secret=params['api_key_secret'],
        resource_owner_key=params['access_token'],
        resource_owner_secret=params['access_token_secret']
    )

  def handle_error(self, res):
    try:
        res.raise_for_status()
    except requests.HTTPError as e:
        print(res.json())
        raise e
    return res

  def fetchData(self):
    # Fetch all pages from Scrapbox
    pages = []
    skip = 0

    while (True):
        params = urllib.parse.urlencode({
            'sort': 'created',
            'skip': skip,
        })
        
        res = requests.get(
            url=f'{App.SCRAPBOX_API_ROOT}/pages/{App.SCRAPBOX_PROJECT_NAME}?{params}'
        )
        json = self.handle_error(res).json()
        for page in json['pages']:
            if (page['pin'] == 0 and page['image']):
                pages.append(page)

        cnt = len(json['pages'])

        print(f'{cnt} of {json["count"]} pages fetched from Scrapbox.')

        skip += cnt
        if (cnt < 100):
            break

    # Fetch images from Scrapbox
    images = []
    for page in pages:
        res = requests.get(page['image'])
        images.append(self.handle_error(res).content)

        print(f'{page["image"]} fetched.')
    images.reverse()
    
    print('Fetch images from Scrapbox complete.')

    # Upload image to Twitter and get media ID
    for image in images:
        self.media_ids.append(self.upload_to_twitter(image))

    print('Upload images to Twitter complete.')

  def upload_to_twitter(self, image):
    # Split files and upload them
    # https://developer.twitter.com/en/docs/twitter-api/v1/media/upload-media/uploading-media/chunked-media-upload

    url = f'{App.TWITTER_MEDIA_API_ROOT}/upload.json'
    total_bytes = len(image)

    print('INIT')

    res = self.oauth.post(url=url, data={
        'command': 'INIT',
        'total_bytes': total_bytes,
        'media_type': 'image/png',
    })
    media_id = self.handle_error(res).json()['media_id_string']
    print(f'Media ID: {media_id}')

    print('APPEND')

    segment_id = 0
    bytes_sent = 0
    file = BytesIO(image)

    while (bytes_sent < total_bytes):
        res = self.oauth.post(url=url,
            data={
            'command': 'APPEND',
            'media_id': media_id,
            'segment_index': segment_id,
            },
            files={
                'media': file.read(4*1024*1024),
            }
        )
        self.handle_error(res)

        segment_id += 1
        bytes_sent = file.tell()

        print(f'{bytes_sent} of {total_bytes} bytes uploaded.')

    print('Upload chunks complete.')

    print('FINALIZE')

    res = self.oauth.post(url=url, data={
        'command': 'FINALIZE',
        'media_id': media_id,
    })

    self.check_status(
        self.handle_error(res).json().get('processing_info', None),
        url,
        media_id
    )

    return media_id

  def check_status(self, processing_info, url, media_id):
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

    res = self.oauth.get(url=url, data={
        'command': 'STATUS',
        'media_id': media_id
    })
    self.check_status(
      self.handle_error(res).json().get('processing_info', None),
      url,
      media_id
    )
  
  def tweet(self, text, media_ids = []):
    res = self.oauth.post(
        f'{App.TWITTER_API_V2_ROOT}/tweets',
        json={
            'text': text,
            'media': {
                'media_ids': media_ids,
            },
        }
    )

    self.handle_error(res)

    print('\n'.join([
        'tweet complete',
        f'  text: {text}',
        f'  media_ids: {media_ids}',
    ]))

  def run(self):
    self.fetchData()
    for media_id in self.media_ids:
      self.tweet(text=App.TWEET_HASHTAG, media_ids=[media_id])