# -*- coding: utf-8 -*-

import string
from random import choice
from functools import wraps
from itertools import chain
from flask import redirect, url_for, render_template, g, current_app
from flask.ext.mail import Message
from .nipap import NipapApi
from .exts import mail


def get_api():
    api = getattr(g, '_api', None)
    if api is None:
        api = g._api = NipapApi(current_app.config['APP_ID'])
        uri = 'http://%s:%s@%s' % (current_app.config['API_USER'],
                  current_app.config['API_PASS'], current_app.config['API_HOST'])
        g._api.connect(uri)

    return api


def wizard_form_process(router_id, email, hostname, prefix_len):
    """Process the data gathered from the input form, by performing all steps
       needed to assign enough ips for the router model of the user. """

    from .models import db, IPRequest
    # add new request to database
    router_db = current_app.config['ROUTER_DB']
    r = IPRequest(hostname, email, router_id)
    db.session.add(r)
    db.session.commit()

    # allocate mesh IPs
    router = router_db_get_entry(router_db, router_id)
    ip_mesh_num = 2 if router['dualband'] else 1
    get_api().allocate_ips(current_app.config['API_POOL_MESH'], r.id, r.email,
        r.hostname, ip_mesh_num)

    # allocate HNA network
    get_api().allocate_ips(current_app.config['API_POOL_HNA'], r.id, r.email,
        r.hostname, prefix_len = prefix_len)

    url = url_for(".wizard_activate", request_id=r.id,
                  signed_token=r.gen_signed_token(), _external=True)
    send_email(email, r.hostname, router, url)


def gen_random_hash(length):
    digits = string.ascii_letters + string.digits
    return ''.join(choice(digits) for x in range(length))


def send_email(email, hostname, router, url):
    body = render_template('email.txt',
        router = router['name'],
        url = url
    )

    msg = Message("[Freifunk Berlin] Konfiguration - %s" % hostname,
              sender=current_app.config['MAIL_FROM'],
              recipients=[email],
              body = body)
    mail.send(msg)

def _get_firmwares_for_router(base_url, data):
    firmware_id = data['id']
    if 'firmware_no_suffix' in data and data['firmware_no_suffix']:
        firmware_id = firmware_id[:-1]

    prefix =  "%s/openwrt-%s-%s" % (data['target'], '-'.join(firmware_id), data['fs'])
    return dict([(x, "%s/%s-%s.bin" % (base_url, prefix, x)) for x in ['sysupgrade', 'factory']])

def router_db_get_entry(router_db, router_id, base_url = None):
    if router_id is None:
        return None

    cursor = router_db
    data = dict([(k,v) for k,v in cursor.items() if k != 'entries'])
    keys = router_id.split('/')
    for n in keys:
        cursor = cursor['entries'][n]

        # merge data
        for k,v in cursor.items():
            if k != 'entries':
                data[k] = v

    data['target'] = keys[0]
    data['id'] = keys
    data['firmwares'] = _get_firmwares_for_router(base_url, data)

    return data

def router_db_has_entry(router_db, router_id):
    try:
        return router_db_get_entry(router_db, router_id)
    except KeyError:
        return False

def router_db_list(router_db):
    for target, subtargets  in sorted(router_db['entries'].items()):
        for subtarget, profiles in sorted(subtargets['entries'].items()):
            for profile, entries in sorted(profiles['entries'].items()):
                for device, data in sorted(entries['entries'].items()):
                    name = "%s/%s/%s/%s" % (target, subtarget, profile, device)
                    yield (name, data)
