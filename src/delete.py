# coding: utf-8

from flask import Flask
from flask import g, session, request, url_for, flash
from flask import redirect, render_template
from flask_oauthlib.client import OAuth
import json, datetime, time
import syslog

# Tokens are generated at https://apps.twitter.com/
with open('config.json') as cf:
    config = json.load(cf)


app = Flask(__name__)
app.debug = True
app.secret_key = 'development'

oauth = OAuth(app)

max_tweets_to_process = 5000

sleep_seconds = 60

days_to_keep = 7

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
        deleted_count = 0
        evaluated_count = 0
        max_id = 0 
        batch = 0
        while (deleted_count < max_tweets_to_process ):
            batch += 1
            syslog.syslog ("Currently working on batch # %d" % batch)
            if (max_id > 0):
                req = "statuses/user_timeline.json?count=200&max_id=%d&include_rts=true" % max_id
            else:
                req = "statuses/user_timeline.json?count=200&include_rts=true"
            syslog.syslog ("Making request: %s" % req)
            resp = twitter.request(req)
            if resp.status == 200:
                tweets = resp.data
                syslog.syslog ("Got %d more tweets from Twitter" % len(tweets))
                if (len(tweets) == 0):
                    syslog.syslog ("Sleeping for %d seconds since we got nothing back from Twitter" % sleep_seconds)
                    time.sleep(sleep_seconds)
                else:
                    for tweet in tweets:
                        evaluated_count += 1
                        if (max_id == 0 or tweet['id'] < max_id):
                            max_id = tweet['id']-1
                            syslog.syslog ("max_id is now %d" % max_id)
                    tweets_to_delete = delete_tweets(tweets, days_to_keep)
                    for tweet in tweets_to_delete:
                        if (tweet['retweeted']):
#                            syslog.syslog("Skipping tweet %d as it is a retweet" % tweet['id'])
                            syslog.syslog("Un-retweeting tweet %d" % tweet['id'])
                            r = twitter.post("statuses/unretweet/%d.json" % tweet['id'], data={ 
                                    "id": tweet['id']
                                })
                            if (r.status < 400):
                                syslog.syslog ("Unretweeted tweet #%d, response code: %d" % (tweet['id'], r.status))
                            else:
                                syslog.syslog ("Bad status returned for tweet %d, code: %d, data: %s" % (tweet['id'], r.status, r.data))
                                return;

                       
                        else: 
                            deleted_count += 1
                            syslog.syslog ("About to delete Tweet #%d with timestamp %s" % (tweet['id'], tweet['created_at']))
                            r = twitter.post("statuses/destroy/%d.json" % tweet['id'], data={ 
                                    "id": tweet['id']
                                })
                            if (r.status < 400):
                                syslog.syslog ("Deleted tweet #%d, response code: %d" % (tweet['id'], r.status))
                            else:
                                syslog.syslog ("Bad status returned for tweet %d, code: %d, data: %s" % (tweet['id'], r.status, r.data))
                                return;
                    syslog.syslog ("Looked at %d tweets so far, deleted %d, max_id is now %d" % (evaluated_count, deleted_count, max_id))
                    time.sleep(1)
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
        else: 
            syslog.syslog ("Skipping Tweet #%d with timestamp %s" % (tweet['id'], tweet['created_at']))
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
    app.run(host='0.0.0.0')
