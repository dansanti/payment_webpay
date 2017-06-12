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

    def _webpay_form_get_tx_from_data(self, cr, uid, data, context=None):
        reference, txn_id = data.get('item_number'), data.get('txn_id')
        if not reference or not txn_id:
            error_msg = _('Paypal: received data with missing reference (%s) or txn_id (%s)') % (reference, txn_id)
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        # find tx -> @TDENOTE use txn_id ?
        tx_ids = self.pool['payment.transaction'].search(cr, uid, [('reference', '=', reference)], context=context)
        if not tx_ids or len(tx_ids) > 1:
            error_msg = 'Paypal: received data for reference %s' % (reference)
            if not tx_ids:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        return self.browse(cr, uid, tx_ids[0], context=context)

    def _webpay_form_validate(self, cr, uid, tx, data, context=None):
        status = data.get('payment_status')
        res = {
            'acquirer_reference': data.get('txn_id'),
            'paypal_txn_type': data.get('payment_type'),
        }
        if status in ['Completed', 'Processed']:
            _logger.info('Validated Paypal payment for tx %s: set as done' % (tx.reference))
            res.update(state='done', date_validate=data.get('payment_date', fields.datetime.now()))
            return tx.write(res)
        elif status in ['Pending', 'Expired']:
            _logger.info('Received notification for Paypal payment %s: set as pending' % (tx.reference))
            res.update(state='pending', state_message=data.get('pending_reason', ''))
            return tx.write(res)
        else:
            error = 'Received unrecognized status for Paypal payment %s: %s, set as error' % (tx.reference, status)
            _logger.info(error)
            res.update(state='error', state_message=error)
            return tx.write(res)

    @http.route([
        '/payment/webpay/return/<model("payment.acquirer"):acquirer_id>',
        '/payment/webpay/test/return',
    ], type='http', auth='public', csrf=False, website=True)
    def webpay_form_feedback(self, acquirer_id=None, **post):
        """ Webpay contacts using GET, at least for accept """
        _logger.info('Webpay: entering form_feedback with post data %s', pprint.pformat(post))  # debug
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        resp = request.registry['payment.transaction'].getTransaction(cr, uid, [], acquirer_id, post['token_ws'], context=context)
        _logger.info(resp)
        '''
            TSY: Autenticación exitosa
            TSN: Autenticación fallida.
            TO6: Tiempo máximo excedido para autenticación.
            ABO: Autenticación abortada por tarjetahabiente.
            U3: Error interno en la autenticación.
            Puede ser vacío si la transacción no se autenticó.
        '''
        if resp.VCI in ['TSY']:
            request.registry['payment.transaction'].form_feedback(cr, uid, resp, 'webpay', context=context)
        urequest = urllib2.Request(resp.urlRedirection, werkzeug.url_encode({'token_ws': post['token_ws'], }))
        uopen = urllib2.urlopen(urequest)
        resp = uopen.read()
        values={
            'webpay_redirect': resp,
        }
        return request.website.render('payment_webpay.webpay_redirect', values)


    @http.route([
        '/payment/webpay/final',
        '/payment/webpay/test/final',
    ], type='http', auth='public', csrf=False, website=True)
    def final(self, **post):
        """ Webpay contacts using GET, at least for accept """
        _logger.info('Webpay: entering End with post data %s', pprint.pformat(post))  # debug
        cr, uid, context = request.cr, SUPERUSER_ID, request.context
        return werkzeug.utils.redirect('/shop/payment/validate')


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
