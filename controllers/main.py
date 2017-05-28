# -*- coding: utf-8 -*-
import logging
import pprint
import werkzeug
import urllib2

from openerp import http, SUPERUSER_ID
from openerp.addons.web.http import request
from openerp.addons.payment.models.payment_acquirer import ValidationError

_logger = logging.getLogger(__name__)


class WebpayController(http.Controller):
    _accept_url = '/payment/webpay/test/accept'
    _decline_url = '/payment/webpay/test/decline'
    _exception_url = '/payment/webpay/test/exception'
    _cancel_url = '/payment/webpay/test/cancel'

    @http.route([
        '/payment/webpay/accept', '/payment/webpay/test/accept',
        '/payment/webpay/decline', '/payment/webpay/test/decline',
        '/payment/webpay/exception', '/payment/webpay/test/exception',
        '/payment/webpay/cancel', '/payment/webpay/test/cancel',
    ], type='http', auth='none')
    def webpay_form_feedback(self, **post):
        """ Webpay contacts using GET, at least for accept """
        _logger.info('Webpay: entering form_feedback with post data %s', pprint.pformat(post))  # debug
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        request.registry['payment.transaction'].form_feedback(cr, uid, post, 'webpay', context=context)
        return werkzeug.utils.redirect(post.pop('return_url', '/'))


    @http.route(['/payment/webpay/s2s/create_json'], type='json', auth='public', csrf=False)
    def webpay_s2s_create_json(self, **kwargs):
        data = kwargs
        acquirer_id = int(data.get('acquirer_id'))
        acquirer = request.env['payment.acquirer'].browse(acquirer_id)
        new_id = acquirer.s2s_process(data)
        return new_id

    @http.route(['/payment/webpay/s2s/create'], type='http', auth='public', methods=["POST"], csrf=False)
    def webpay_s2s_create(self, **post):
        acquirer_id = int(post.get('acquirer_id'))
        acquirer = request.env['payment.acquirer'].browse(acquirer_id)
        acquirer.s2s_process(post)
        return werkzeug.utils.redirect(post.get('return_url', '/'))

    @http.route(['/payment/webpay/s2s/feedback'], auth='none', csrf=False)
    def feedback(self, **kwargs):
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        payment = request.registry.get('payment.transaction')
        try:
            tx = payment._webpay_form_get_tx_from_data(cr, uid, kwargs, context=context)
            payment._webpay_s2s_validate(tx)
        except ValidationError:
            return 'ko'

        return 'ok'

    @http.route(['/payment/webpay/redirect'],  type='http', auth='public', methods=["POST"], csrf=False, website=True)
    def redirect_webpay(self, **post):
        _logger.info(post)
        acquirer_id = int(post.get('acquirer_id'))
        acquirer = request.env['payment.acquirer'].browse(acquirer_id)
        result =  acquirer.initTransaction(post)
        urequest = urllib2.Request(result['url'], werkzeug.url_encode({'token_ws': result['token']}))
        uopen = urllib2.urlopen(urequest)
        resp = uopen.read()
        values={
            'webpay_redirect': resp,
        }
        return request.website.render('payment_webpay.webpay_redirect', values)
