from flask import request, jsonify, Response, json, redirect, abort, render_template, session, json
from hackhub import app, spaceapi, get_db
from member import Member
from status import Status, new_status
from event import new_event, recent_events
from bank import bank
from door_code import new_code
from decorators import login_required
from casclient import client as casclient
import datetime


@app.route('/')
def the_homepage():
    return render_template('front_home.html')

@app.route('/about-us/')
def the_about_us():
    return render_template('front_home.html')

@app.route('/contact-us/')
def the_contact():
    return render_template('front_home.html')

@app.route('/blog/')
def the_blog():
    return redirect('http://www.hackerdeen.org.uk/blog/')

@app.route('/spaceapi')
def spaceapi_json():
    s = spaceapi
    s['state'] = Status().status
    s['state']['icon'] = {}
    s['state']['icon']['open'] = 'https://57north.org.uk/57_North_CLL_open.png'
    s['state']['icon']['closed'] = 'https://57north.org.uk/57_North_CLL_closed.png'
    s['events'] = []
    for event in recent_events():
        s['events'].append({'name': event[1],
                            'type': event[2],
                            'timestamp': event[3],
                            'extra': event[4]})
                            
    r = jsonify(s)
    r.headers['Access-Control-Allow-Origin'] = '*'
    r.headers['Cache-Control'] = 'no-cache'
    return r

@app.route('/hub/')
@login_required
def hub_home():
    m = Member(session['username'])  
    return render_template('home.html', profile=m.get_profile(), 
                           status=Status().status, paid=m.is_paid(), 
                           username=session['username'], payment_history=m.payment_history())

@app.route('/hub/login')
def hub_login():
    return redirect(casclient.get_login_url())

@app.route('/hub/login/ticket')
def hub_login_ticket():
    try:
        ticket = request.args["ticket"]
        user, attributes, pgtiou = casclient.verify_ticket(ticket)
        if not user:
            raise Exception()
    except:
        return redirect('/hub/login')
    try:
        m = Member(user)
    except:
        session['application_username'] = user
        return redirect('/hub/apply-for-membership')
    session['username'] = user
    return redirect('/hub/')

@app.route('/hub/logout')
def hub_logout():
    session.clear()
    return redirect('/')

@app.route('/hub/apply-for-membership', methods=['GET', 'POST'])
def hub_apply_for_membership():
    if not session.get('application_username'):
        return redirect('/hub/')
    try:
        m = Member(session['application_username'])
    except:
        pass
    else:
        session['username'] = session['application_username']
        del session['application_username']
        return redirect('/hub/')

    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT 1 FROM application WHERE username=?',
        (session['application_username'],))
    if cur.fetchone():
        cur.close()
        return render_template('membership_apply_thanks.html', status=Status().status)
    cur.close()

    if request.method == 'GET':
        return render_template('membership_apply.html', status=Status().status)
    else:
        try:
            username = session['application_username']
            realname = request.form['realname']
            nickname = request.form['nickname']
            email = request.form['email']
            address = request.form['address']
        except KeyError:
            return redirect('/hub/apply-for-membership')

        cur = db.cursor()
        cur.execute("""insert into application (username, realname,
            nickname, email, address, received) values (?, ?, ?, ?, ?, strftime('%s', 'now'))""",
            (username, realname, nickname, email, address))
        db.commit()
        cur.close()

        return render_template('membership_apply_thanks.html', status=Status().status)

@app.route('/hub/profile')
@login_required
def hub_profile():
    return render_template('profile.html', profile=Member(session['username']).get_profile(), 
                           status=Status().status)

@app.route('/hub/profile/edit', methods=['GET', 'POST'])
@login_required
def hub_profile_edit():
    if request.method == 'GET':
        return render_template('profile_edit.html', profile=Member(session['username']).get_profile(), 
                               status=Status().status)
    elif request.method == 'POST':
        updatable = ['realname', 'nickname', 'email', 'twitter', 'irc', 'github']
        update = {}
        for x in request.form:
            if x in updatable:
                update[x] = None if request.form[x] == 'None' else request.form[x]
                m = Member(session['username'])
                m.update_profile(update)
        return redirect('/hub/')
@app.route('/hub/profile/emails')
@login_required
def profile_emails():
    m = Member(session['username'])
    uprefs = m.get_email_prefs()
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT code, description FROM email_events")
    events = cur.fetchall()
    return render_template("email_prefs.html", uprefs=uprefs, events=events)

@app.route('/hub/profile/email_toggle/<event>')
@login_required
def profile_email_toggle(event):
    m = Member(session['username'])
    if m.get_email_prefs()[event]:
        m.set_email_pref(event, 0)
    else:
        m.set_email_pref(event, 1)
    return redirect('/hub/profile/emails')
        
               
@app.route('/hub/payments')
@login_required
def hub_payments():
    return render_template('payments.html', payments=Member(session['username']).get_payments(),
                           status=Status().status)

@app.route('/hub/status')
@login_required
def hub_status():
    status = Status().status
    status['lastchange_utc_forhumans'] = datetime.datetime.fromtimestamp(int(status['lastchange'])).strftime("%c")
    return render_template('status.html', status=status)
    
@app.route('/hub/status/update', methods=['POST', 'GET'])
@login_required
def hub_status_update():
    if request.method == 'GET':
        return render_template('status_update.html', status=Status().status)
    elif request.method == 'POST':
        if not ( request.form['state'] == '0' or request.form['state'] == '1' ):
            abort(400)
        new_status(request.form['state'], request.form['message'], session['username'])
        return redirect('/hub/status')

@app.route('/hub/door')
@login_required
def door():
    return render_template("unlock.html")
    
from unlock import unlock

@app.route('/hub/open_door')
@login_required
def open_door():
    if Member(session['username']).is_active():
        success, message = unlock(session['username'])
        if success:
            return render_template("open_door.html", response=message)
        else:
            return render_template("open_door.html", response="Well that didn't work... " + message)
    else:
        return render_template("open_door.html", response="You have to pay to do that :)")

@app.route('/hub/door_code')
@login_required
def door_code():
    if Member(session['username']).is_active():
        return render_template("door_code.html", code=new_code(session['username']))
    else:
        return render_template("open_door.html", response="You have to be an active member to do that.")
        
@app.route('/hub/so_form')
@login_required
def so_form():
    return render_template("standing_order.html", member=Member(session['username']),
                           bank=bank)


@app.route('/hub/setup_payment')
@login_required
def setup_payment():
    return render_template("setup_payment.html", member=Member(session['username']),
                           bank=bank)

