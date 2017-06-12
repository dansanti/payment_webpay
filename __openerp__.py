# -*- coding: utf-8 -*-

{
    'name': 'Webpay Payment Acquirer',
    'category': 'Accounting',
    'author': 'Daniel Santibáñez Polanco',
    'summary': 'Payment Acquirer: Webpay Implementation',
    'website': 'https://odoocoop.cl',
    'version': "9.0.5.0",
    'description': """Webpay Payment Acquirer""",
    'depends': ['payment'],
    'python-depends':[
        'suds',
        'py-wsse',
        # En Debian/Ubuntu:
        # sudo apt-get install libssl-dev libxml2-dev libxmlsec1-dev
        #    Sistemas basados en RedHat:
        # sudo yum install openssl-devel libxml2-devel xmlsec1-devel xmlsec1-openssl-devel libtool-ltdl-devel
    ],
    'data': [
        'views/webpay.xml',
        'views/payment_acquirer.xml',
        'views/payment_transaction.xml',
        'data/webpay.xml',
    ],
    'installable': True,
}
