# -*- coding: utf-'8' "-*-"

import datetime
from hashlib import sha1
import logging
import socket
from openerp import SUPERUSER_ID
from openerp import api, models, fields, _
from openerp.tools import float_round, DEFAULT_SERVER_DATE_FORMAT
from openerp.tools.float_utils import float_compare, float_repr
from openerp.tools.safe_eval import safe_eval
from base64 import b64decode

_logger = logging.getLogger(__name__)
try:
    from suds.client import Client
    from suds.wsse import Security, Timestamp
    from .wsse.suds import WssePlugin
    from suds.transport.https import HttpTransport
except:
    _logger.info("No Load suds or wsse")

URLS ={
    'integ': 'https://webpay3gint.transbank.cl/WSWebpayTransaction/cxf/WSWebpayService?wsdl',
    'test': 'https://webpay3gint.transbank.cl/WSWebpayTransaction/cxf/WSWebpayService?wsdl',
    'prod': 'https://webpay3g.transbank.cl//WSWebpayTransaction/cxf/WSWebpayService?wsdl',
}

class PaymentAcquirerWebpay(models.Model):
    _inherit = 'payment.acquirer'

    @api.model
    def _get_providers(self,):
        providers = super(PaymentAcquirerWebpay, self)._get_providers()
        providers.append(['webpay', 'Webpay'])
        return providers

    webpay_commer_code = fields.Char(
        string="Commerce Code",)
    webpay_private_key = fields.Binary(
        string="User Private Key",)
    webpay_public_cert = fields.Binary(
        string="User Public Cert",)
    webpay_cert = fields.Binary(
        string='Webpay Cert',)
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
            'cmd': '_xclick',
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
            'return_url': base_url + "/my/transaction/" + str(self.id)
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
        )

    """
    initTransaction

    Permite inicializar una transaccion en Webpay.
    Como respuesta a la invocacion se genera un token que representa en forma unica una transaccion.
    """
    def initTransaction(self, post, buyOrder=1123, sessionId=2):

        client = self.get_client()
        client.options.cache.clear()
        init = client.factory.create('wsInitTransactionInput')

        init.wSTransactionType = client.factory.create('wsTransactionType').TR_NORMAL_WS

        init.commerceId = self.webpay_commer_code

        init.buyOrder = buyOrder
        init.sessionId = sessionId
        init.returnURL = post['return_url']
        init.finalURL = post['return_url']

        detail = client.factory.create('wsTransactionDetail')
        detail.amount = post['amount']

        detail.commerceCode = self.webpay_commer_code
        detail.buyOrder = buyOrder

        init.transactionDetails.append(detail)
        init.wPMDetail=client.factory.create('wpmDetailInput')

        wsInitTransactionOutput = client.service.initTransaction(init)
        _logger.info(wsInitTransactionOutput)

        return wsInitTransactionOutput


class PaymentTxWebpay(models.Model):
    _inherit = 'payment.transaction'

    """
    getTransaction

    Permite obtener el resultado de la transaccion una vez que
    Webpay ha resuelto su autorizacion financiera.
    """
    def getTransaction(self, token):

        client = WebpayNormal.get_client(url, config.getPrivateKey(), config.getPublicCert(), config.getWebPayCert())
        client.options.cache.clear()

    	transactionResultOutput = client.service.getTransactionResult(token)
    	acknowledge = WebpayNormal.acknowledgeTransaction(token)

        return transactionResultOutput


    """
    acknowledgeTransaction
    Indica  a Webpay que se ha recibido conforme el resultado de la transaccion
    """
    def acknowledgeTransaction(self, token):
        client = WebpayNormal.get_client(url, config.getPrivateKey(), config.getPublicCert(), config.getWebPayCert())
        client.options.cache.clear()

        acknowledge = client.service.acknowledgeTransaction(token)

        return acknowledge

class PaymentMethod(models.Model):
    _inherit = 'payment.method'
