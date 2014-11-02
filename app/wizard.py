# -*- coding: utf-8 -*-

import re

from itertools import chain
from flask import Blueprint, render_template, redirect, url_for, current_app,\
                  request, g
from wtforms import SelectField
from .utils import wizard_form_process, send_email, get_api,\
                   router_db_get_entry, router_db_has_entry, router_db_list
from .models import IPRequest, EmailForm, DestroyForm
from .exts import db


wizard = Blueprint('wizard', __name__)


@wizard.route('/wizard/config/<token>')
def wizard_get_config(token):
    r = IPRequest.query.filter_by(token=token).one()
    if not r.verified:
        raise Exception('Request has not been verified yet')

    return render_template('wizard/show_config.html', ips=r.ips_pretty, router=r.router)


@wizard.route('/')
@wizard.route('/wizard/routers/<path:router_id>')
def wizard_select_router(router_id = None):
    router_db = current_app.config['ROUTER_DB']
    if router_db_has_entry(router_db, router_id):
        return redirect(url_for('.wizard_form', router_id = router_id))

    routers = router_db_list(router_db)
    return render_template('wizard/select_router.html', routers=routers)


@wizard.route('/wizard/forms/<path:router_id>', methods=['GET', 'POST'])
def wizard_form(router_id):
    # add location type field dynamically (values are set in config)
    prefix_defaults = current_app.config['PREFIX_DEFAULTS']
    choices = [(k,k) for k in prefix_defaults.keys()]
    setattr(EmailForm, 'location_type', SelectField('Ort', choices=choices))

    form = EmailForm()
    if form.validate_on_submit():
        r = wizard_form_process(
            router_id,
            form.hostname.data,
            form.email.data,
            prefix_defaults[form.location_type.data])

        url = url_for(".wizard_activate", request_id=r.id,
                      signed_token=r.token_activation, _external=True)
        subject = "[Freifunk Berlin] Aktivierung - %s" % r.hostname
        data = {
            'hostname': r.hostname,
            'router': r.router['name'], 'url': url
        }
        send_email(r.email, subject, "wizard/email_activation.txt", data)
        return redirect(url_for('.wizard_send_email'))

    router_db = current_app.config['ROUTER_DB']
    router = router_db_get_entry(router_db, router_id)
    return render_template('wizard/form.html', form = form, router = router)


@wizard.route('/wizard/email_sent')
def wizard_send_email():
    return render_template('wizard/waiting_for_confirmation.html')


@wizard.route('/wizard/activate/<int:request_id>/<signed_token>')
def wizard_activate(request_id, signed_token):
    r = IPRequest.query.get(request_id)
    if not r.verified:
        r.activate(signed_token)
        url = url_for(".wizard_destroy", request_id=r.id,
                      signed_token=r.token_destroy, _external=True)
        subject = "[Freifunk Berlin] Konfiguration - %s" % r.hostname
        send_email(r.email, subject, 'wizard/email_config.txt', {'request' : r,
            'url':url})

    return redirect(url_for('.wizard_get_config', token = r.token))


@wizard.route('/wizard/destroy/<int:request_id>/<signed_token>', methods=['GET', 'POST'])
def wizard_destroy(request_id, signed_token):
    form = DestroyForm(request_id=request_id, token=signed_token)
    r = IPRequest.query.get(request_id)
    if form.validate_on_submit():
        r.destroy(form.token.data)
        return render_template('wizard/destroy_success.html', hostname = r.hostname)

    url = url_for('.wizard_destroy', request_id = r.id, signed_token = signed_token)
    return render_template('wizard/destroy_form.html', request = r, form = form, url =  url)
