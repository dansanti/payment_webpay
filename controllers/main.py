# -*- coding: utf-8 -*-
import logging
import pprint
import werkzeug
from odoo import http
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.http import request
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import urllib3
    urllib3.disable_warnings()
    pool = urllib3.PoolManager()
except:
    _logger.warning("No Load urllib3")
    pass


class WebpayController(http.Controller):
    _accept_url = '/payment/webpay/test/accept'
    _decline_url = '/payment/webpay/test/decline'
    _exception_url = '/payment/webpay/test/exception'
    _cancel_url = '/payment/webpay/test/cancel'

    def _webpay_form_get_tx_from_data(self, cr, uid, data, context=None):
        _logger.info('Webpay: entering form_get_tx with post data %s', pprint.pformat(data))  # debug
        reference, txn_id = data.get('item_number'), data.get('txn_id')
        if not reference or not txn_id:
            error_msg = _('Paypal: received data with missing reference (%s) or txn_id (%s)') % (reference, txn_id)
            _logger.warning(error_msg)
            raise ValidationError(error_msg)

        # find tx -> @TDENOTE use txn_id ?
        tx_ids = self.pool['payment.transaction'].search(cr, uid, [('reference', '=', reference)], context=context)
        if not tx_ids or len(tx_ids) > 1:
            error_msg = 'Paypal: received data for reference %s' % (reference)
            if not tx_ids:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.warning(error_msg)
            raise ValidationError(error_msg)
        return self.browse(cr, uid, tx_ids[0], context=context)

    def _webpay_form_validate(self, cr, uid, tx, data, context=None):
        _logger.info('Webpay: entering form_validate with post data %s', pprint.pformat(data))  # debug
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
            _logger.warning('Received notification for Paypal payment %s: set as pending' % (tx.reference))
            res.update(state='pending', state_message=data.get('pending_reason', ''))
            return tx.write(res)
        else:
            error = 'Received unrecognized status for Paypal payment %s: %s, set as error' % (tx.reference, status)
            _logger.warning(error)
            res.update(state='error', state_message=error)
            return tx.write(res)

    @http.route([
        '/payment/webpay/return/<model("payment.acquirer"):acquirer_id>',
        '/payment/webpay/test/return',
    ], type='http', auth='public', csrf=False, website=True)
    def webpay_form_feedback(self, acquirer_id=None, **post):
        """ Webpay contacts using GET, at least for accept """
        _logger.warning('Webpay: entering form_feedback with post data %s', pprint.pformat(post))  # debug
        token_ws = post.get('token_ws') or post.get('TBK_TOKEN')
        try:
            resp = request.env['payment.transaction'].getTransaction(acquirer_id, token_ws)
        except:
            resp = False
            if not post.get('TBK_TOKEN'):
                raise UserError('Ha ocurrido un error al obtener la transacción desde Webpay')
        '''
            TSY: Autenticación exitosa
            TSN: Autenticación fallida.
            TO6: Tiempo máximo excedido para autenticación.
            ABO: Autenticación abortada por tarjetahabiente.
            U3: Error interno en la autenticación.
            Puede ser vacío si la transacción no se autenticó.
        '''
        if resp:
            request.env['payment.transaction'].sudo().form_feedback(resp, 'webpay')
            if resp.VCI in ['TSY'] and str(resp.detailOutput[0].responseCode) in ['0']:
                values = {
                            'url': resp.urlRedirection,
                            'token_ws': token_ws
                        }
                return request.render('payment_webpay.webpay_redirect', values)
            request.website.sale_reset()
        elif post.get('TBK_ORDEN_COMPRA'):
            tx = request.env['payment.transaction'].sudo().search([
                            ('reference', '=', post.get('TBK_ORDEN_COMPRA'))
                            ])
            tx.write({'state': 'error', 'state_message': 'Pago cancelado (abortado en formulario Webpay)'})
        return werkzeug.utils.redirect('/shop/confirmation')

    @http.route([
        '/payment/webpay/final/<model("payment.acquirer"):acquirer_id>',
    ], type='http', auth='public', csrf=False, website=True)
    def final(self, acquirer_id=False, **post):
        """ Webpay contacts using GET, at least for accept """
        _logger.info('Webpay: entering End with post data %s', pprint.pformat(post))  # debug
        if post.get('TBK_TOKEN'):
            return self.webpay_form_feedback(acquirer_id, **post)
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
        payment = request.env['payment.transaction']
        try:
            tx = payment._webpay_form_get_tx_from_data(kwargs)
            payment._webpay_s2s_validate(tx)
        except ValidationError:
            return 'ko'
        return 'ok'

    @http.route(['/payment/webpay/redirect'],  type='http', auth='public', methods=["POST"], csrf=False, website=True)
    def redirect_webpay(self, **post):
        acquirer_id = int(post.get('acquirer_id'))
        acquirer = request.env['payment.acquirer'].browse(acquirer_id)
        result = acquirer.initTransaction(post)
        urequest = pool.request(
                                'GET',
                                result['url'],
                                {
                                    'token_ws': result['token']
                                })
        resp = urequest.data
        values = {
            'webpay_redirect': resp,
        }
        return request.render('payment_webpay.webpay_redirect', values)
