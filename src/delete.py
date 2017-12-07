# coding: utf-8

from flask import Flask
from flask import g, session, request, url_for, flash
from flask import redirect, render_template
from flask_oauthlib.client import OAuth
import json, datetime

# Tokens are generated at https://apps.twitter.com/
with open('config.json') as cf:
    config = json.load(cf)


app = Flask(__name__)
app.debug = True
app.secret_key = 'development'

oauth = OAuth(app)

max_tweets_to_process = 1000


twitter = oauth.remote_app(
    'twitter',
    consumer_key=config['consumer_key'],
    consumer_secret=config['consumer_secret'],
    base_url='https://api.twitter.com/1.1/',
    request_token_url='https://api.twitter.com/oauth/request_token',
    access_token_url='https://api.twitter.com/oauth/access_token',
    authorize_url='https://api.twitter.com/oauth/authorize'
)


@twitter.tokengetter
def get_twitter_token():
    if 'twitter_oauth' in session:
        resp = session['twitter_oauth']
        return resp['oauth_token'], resp['oauth_token_secret']


@app.before_request
def before_request():
    g.user = None
    if 'twitter_oauth' in session:
        g.user = session['twitter_oauth']


@app.route('/')
def index():
    tweets = None
    if g.user is not None:
        processed_count = 0
        max_id = 0 
        while (processed_count < max_tweets_to_process ):
            if (max_id > 1):
                req = "statuses/user_timeline.json?count=200&max_id=%d" % max_id
            else:
                req = "statuses/user_timeline.json?count=200"
            resp = twitter.request(req)
            if resp.status == 200:
                tweets = resp.data
                for tweet in tweets:
                    if (max_id == 0 or tweet['id'] < max_id):
                        max_id = tweet['id']
                tweets = delete_tweets(tweets, 1)
                processed_count += len(tweets)
                print ("processed %d tweets so far, max_id is now %d" % (processed_count, max_id))
            else:
                flash('Unable to load tweets from Twitter.')
                break
    return render_template('index.html', tweets=tweets)

def delete_tweets(tweets, threshold_days=365 ):
    filtered_tweets = []
    now =  datetime.datetime.now()

    for tweet in tweets:
        ts = datetime.datetime.strptime(tweet['created_at'],'%a %b %d %H:%M:%S +0000 %Y')
        age = now - ts
        age_days = divmod(age.total_seconds(), 86400)[0]
        if (age_days > threshold_days):
            filtered_tweets.append(tweet)
    return filtered_tweets


@app.route('/tweet', methods=['POST'])
def tweet():
    if g.user is None:
        return redirect(url_for('login', next=request.url))
    status = request.form['tweet']
    if not status:
        return redirect(url_for('index'))
    resp = twitter.post('statuses/update.json', data={
        'status': status
    })

    if resp.status == 403:
        flash("Error: #%d, %s " % (
            resp.data.get('errors')[0].get('code'),
            resp.data.get('errors')[0].get('message'))
        )
    elif resp.status == 401:
        flash('Authorization error with Twitter.')
    else:
        flash('Successfully tweeted your tweet (ID: #%s)' % resp.data['id'])
    return redirect(url_for('index'))

@app.route('/login')
def login():
    callback_url = url_for('oauthorized', next=request.args.get('next'))
    return twitter.authorize(callback=callback_url or request.referrer or None)


@app.route('/logout')
def logout():
    session.pop('twitter_oauth', None)
    return redirect(url_for('index'))


@app.route('/oauthorized')
def oauthorized():
    resp = twitter.authorized_response()
    if resp is None:
        flash('You denied the request to sign in.')
    else:
        session['twitter_oauth'] = resp
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run()
