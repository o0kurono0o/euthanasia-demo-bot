import json
from requests_oauthlib import OAuth1Session
import boto3

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