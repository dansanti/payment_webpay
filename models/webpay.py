# -*- coding: utf-'8' "-*-"

import datetime
from hashlib import sha1
import logging
import socket
from odoo import SUPERUSER_ID
from odoo import api, models, fields
from odoo.tools import float_round, DEFAULT_SERVER_DATE_FORMAT
from odoo.tools.float_utils import float_compare, float_repr
from odoo.tools.safe_eval import safe_eval
from odoo.tools.translate import _
from base64 import b64decode
import os

_logger = logging.getLogger(__name__)
try:
    from suds.client import Client
    from suds.wsse import Security, Timestamp
    from .wsse.suds import WssePlugin
    from suds.transport.https import HttpTransport
    from suds.cache import ObjectCache
    cache_path = "/tmp/{0}-suds".format(os.getuid())
    cache = ObjectCache(cache_path)
except:
    _logger.warning("No Load suds or wsse")

URLS ={
    'integ': 'https://webpay3gint.transbank.cl/WSWebpayTransaction/cxf/WSWebpayService?wsdl',
    'test': 'https://webpay3gint.transbank.cl/WSWebpayTransaction/cxf/WSWebpayService?wsdl',
    'prod': 'https://webpay3g.transbank.cl/WSWebpayTransaction/cxf/WSWebpayService?wsdl',
}

class PaymentAcquirerWebpay(models.Model):
    _inherit = 'payment.acquirer'

    @api.model
    def _get_providers(self,):
        providers = super(PaymentAcquirerWebpay, self)._get_providers()
        return providers

    provider = fields.Selection(
            selection_add=[('webpay', 'Webpay')]
        )
    webpay_commer_code = fields.Char(
            string="Commerce Code"
        )
    webpay_private_key = fields.Binary(
            string="User Private Key",
        )
    webpay_public_cert = fields.Binary(
            string="User Public Cert",
        )
    webpay_cert = fields.Binary(
            string='Webpay Cert',
        )
    webpay_mode = fields.Selection(
            [
                ('normal', "Normal"),
                ('mall', "Normal Mall"),
                ('oneclick', "OneClick"),
                ('completa', "Completa"),
            ],
            string="Webpay Mode",
        )
    environment = fields.Selection(
            selection_add=[('integ', 'Integración')],
        )

    @api.multi
    def _get_feature_support(self):
        res = super(PaymentAcquirerWebpay, self)._get_feature_support()
        res['fees'].append('webpay')
        return res

    def _get_webpay_urls(self):
        url = URLS[self.environment]
        return url

    @api.multi
    def webpay_form_generate_values(self, values):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        values.update({
            'business': self.company_id.name,
            'item_name': '%s: %s' % (self.company_id.name, values['reference']),
            'item_number': values['reference'],
            'amount': values['amount'],
            'currency_code': values['currency'] and values['currency'].name or '',
            'address1': values.get('partner_address'),
            'city': values.get('partner_city'),
            'country': values.get('partner_country') and values.get('partner_country').code or '',
            'state': values.get('partner_state') and (values.get('partner_state').code or values.get('partner_state').name) or '',
            'email': values.get('partner_email'),
            'zip_code': values.get('partner_zip'),
            'first_name': values.get('partner_first_name'),
            'last_name': values.get('partner_last_name'),
            'return_url': base_url + '/payment/webpay/final'
        })
        return values

    @api.multi
    def webpay_get_form_action_url(self,):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return base_url +'/payment/webpay/redirect'

    def get_private_key(self):
        return b64decode(self.webpay_private_key)

    def get_public_cert(self):
        return b64decode(self.webpay_public_cert)

    def get_WebPay_cert(self):
        return b64decode(self.webpay_cert)

    def get_client(self,):
        transport=HttpTransport()
        wsse = Security()

        return Client(
            self._get_webpay_urls(),
            transport=transport,
            wsse=wsse,
            plugins=[
                WssePlugin(
                    keyfile=self.get_private_key(),
                    certfile=self.get_public_cert(),
                    their_certfile=self.get_WebPay_cert(),
                ),
            ],
            cache=cache,
        )

    """
    initTransaction

    Permite inicializar una transaccion en Webpay.
    Como respuesta a la invocacion se genera un token que representa en forma unica una transaccion.
    """
    def initTransaction(self, post):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        client = self.get_client()
        client.options.cache.clear()
        init = client.factory.create('wsInitTransactionInput')

        init.wSTransactionType = client.factory.create('wsTransactionType').TR_NORMAL_WS

        init.commerceId = self.webpay_commer_code

        init.buyOrder = post['item_number']
        init.sessionId = self.company_id.id
        init.returnURL = base_url + '/payment/webpay/return/'+str(self.id)
        init.finalURL =  post['return_url']+'/'+str(self.id)

        detail = client.factory.create('wsTransactionDetail')
        detail.amount = post['amount']

        detail.commerceCode = self.webpay_commer_code
        detail.buyOrder = post['item_number']

        init.transactionDetails.append(detail)
        init.wPMDetail=client.factory.create('wpmDetailInput')

        wsInitTransactionOutput = client.service.initTransaction(init)

        return wsInitTransactionOutput


class PaymentTxWebpay(models.Model):
    _inherit = 'payment.transaction'

    webpay_txn_type = fields.Selection([
            ('VD','Venta Debito'),
            ('VN','Venta Normal'),
            ('VC','Venta en cuotas'),
            ('SI','3 cuotas sin interés'),
            ('S2','cuotas sin interés'),
            ('NC','N Cuotas sin interés'),
        ],
       string="Webpay Tipo Transacción")

    """
    getTransaction

    Permite obtener el resultado de la transaccion una vez que
    Webpay ha resuelto su autorizacion financiera.
    """
    @api.multi
    def getTransaction(self, acquirer_id, token):
        client = acquirer_id.get_client()
        client.options.cache.clear()

        transactionResultOutput = client.service.getTransactionResult(token)
        acknowledge = self.acknowledgeTransaction(acquirer_id, token)

        return transactionResultOutput

    """
    acknowledgeTransaction
    Indica  a Webpay que se ha recibido conforme el resultado de la transaccion
    """
    def acknowledgeTransaction(self, acquirer_id, token):
        client = acquirer_id.get_client()
        client.options.cache.clear()
        acknowledge = client.service.acknowledgeTransaction(token)
        return acknowledge

    @api.model
    def _webpay_form_get_tx_from_data(self, data):
        reference, txn_id = data.buyOrder, data.sessionId
        if not reference or not txn_id:
            error_msg = _('Webpay: received data with missing reference (%s) or txn_id (%s)') % (reference, txn_id)
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        # find tx -> @TDENOTE use txn_id ?
        tx_ids = self.env['payment.transaction'].search([('reference', '=', reference)])
        if not tx_ids or len(tx_ids) > 1:
            error_msg = 'Webpay: received data for reference %s' % (reference)
            if not tx_ids:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.warning(error_msg)
            raise ValidationError(error_msg)
        return tx_ids[0]

    @api.multi
    def _webpay_form_validate(self, data):
        codes = {
                '0' : 'Transacción aprobada.',
                '-1' : 'Rechazo de transacción.',
                '-2' : 'Transacción debe reintentarse.',
                '-3' : 'Error en transacción.',
                '-4' : 'Rechazo de transacción.',
                '-5' : 'Rechazo por error de tasa.',
                '-6' : 'Excede cupo máximo mensual.',
                '-7' : 'Excede límite diario por transacción.',
                '-8' : 'Rubro no autorizado.',
            }
        status = str(data.detailOutput[0].responseCode)
        res = {
            'acquirer_reference': data.detailOutput[0].authorizationCode,
            'webpay_txn_type': data.detailOutput[0].paymentTypeCode,
            'date_validate' : data.transactionDate,
        }
        if status in ['0']:
            _logger.info('Validated webpay payment for tx %s: set as done' % (self.reference))
            res.update(state='done')
        elif status in ['-6', '-7']:
            _logger.warning('Received notification for webpay payment %s: set as pending' % (self.reference))
            res.update(state='pending', state_message=data.get('pending_reason', ''))
        elif status in ['-1', '-4']:
            res.update(state='cancel')
        else:
            error = 'Received unrecognized status for webpay payment %s: %s, set as error' % (self.reference, codes[status])
            _logger.warning(error)
            res.update(state='error', state_message=error)
        return self.write(res)

    def _confirm_so(self):
        if self.state not in ['cancel']:
            return super(PaymentTxWebpay, self)._confirm_so()
        self.sale_order_id.action_cancel()
        return True
