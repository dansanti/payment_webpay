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

_logger = logging.getLogger(__name__)
try:
    from suds.client import Client
    from suds.wsse import Security, Timestamp
    from wsse.suds import WssePlugin
except:
    _logger.info("No Load suds or wsse")

URLS = dict({
    'integ': 'https://webpay3gint.transbank.cl/WSWebpayTransaction/cxf/WSWebpayService?wsdl',
    'test': 'https://webpay3gint.transbank.cl/WSWebpayTransaction/cxf/WSWebpayService?wsdl',
    'prod': 'https://webpay3g.transbank.cl//WSWebpayTransaction/cxf/WSWebpayService?wsdl',
})

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
    environment = fields.Selection(selection_add=[('integ', 'Integración')])

    @api.multi
    def _get_feature_support(self):
        res = super(PaymentAcquirerWebpay, self)._get_feature_support()
        res['fees'].append('webpay')
        return res

    @api.multi
    def get_webpay_urls(self):
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
        })
        return values

    def webpay_get_form_action_url(self, cr, uid, id, context=None):
        acquirer = self.browse(cr, uid, id, context=context)
        return self._get_webpay_urls(cr, uid, acquirer.environment, context=context)

    def get_private_key(self):
        filecontent = base64.b64decode(self.key_file)

    def get_private_key(self):
        filecontent = base64.b64decode(self.key_file)

    def get_private_key(self):
        filecontent = base64.b64decode(self.key_file)


class PaymentTxWebpay(models.Model):
    _inherit = 'payment.transaction'

    """
    initTransaction

    Permite inicializar una transaccion en Webpay.
    Como respuesta a la invocacion se genera un token que representa en forma unica una transaccion.
    """
    def initTransaction(self, amount, buyOrder, sessionId, urlReturn, urlFinal):

        client = WebpayNormal.get_client(url, config.get_private_key(), config.get_public_cert(), config.getWebPayCert())
        client.options.cache.clear();
        init = client.factory.create('wsInitTransactionInput')

        init.wSTransactionType = client.factory.create('wsTransactionType').TR_NORMAL_WS

        init.commerceId = config.getCommerceCode();

        init.buyOrder = buyOrder;
        init.sessionId = sessionId;
        init.returnURL = urlReturn;
        init.finalURL = urlFinal;

        detail = client.factory.create('wsTransactionDetail');
        detail.amount = amount;

        detail.commerceCode = config.getCommerceCode();
        detail.buyOrder = buyOrder;

        init.transactionDetails.append(detail);
        init.wPMDetail=client.factory.create('wpmDetailInput');

        wsInitTransactionOutput = client.service.initTransaction(init);

        return wsInitTransactionOutput;

    """
    getTransaction

    Permite obtener el resultado de la transaccion una vez que
    Webpay ha resuelto su autorizacion financiera.
    """
    def getTransaction(self, token):

        client = WebpayNormal.get_client(url, config.getPrivateKey(), config.getPublicCert(), config.getWebPayCert());
        client.options.cache.clear();

    	transactionResultOutput = client.service.getTransactionResult(token);
    	acknowledge = WebpayNormal.acknowledgeTransaction(token);

        return transactionResultOutput;


    """
    acknowledgeTransaction
    Indica  a Webpay que se ha recibido conforme el resultado de la transaccion
    """
    def acknowledgeTransaction(self, token):
        client = WebpayNormal.get_client(url, config.getPrivateKey(), config.getPublicCert(), config.getWebPayCert());
        client.options.cache.clear();

        acknowledge = client.service.acknowledgeTransaction(token);

        return acknowledge;


    def get_client(self, wsdl_url, our_keyfile_path, our_certfile_path, their_certfile_path):

        transport=HttpTransport()
        wsse = Security()

        return Client(
            wsdl_url,
            transport=transport,
            wsse=wsse,
            plugins=[
                WssePlugin(
                    keyfile=our_keyfile_path,
                    certfile=our_certfile_path,
                    their_certfile=their_certfile_path,
                ),
            ],
        )

class PaymentMethod(models.Model):
    _inherit = 'payment.method'
