# Pasarela de pagos Webpay para Odoo

- Nos basamos en payment_paypal y payment_ogone
- Aún No funcional al 100%
- Falta enviar Detalle completo, solamente se está enviando detalle demo
- Falta Procesar las respuestas de Webpay
- Se modifica a medida de Odoo la librería wsse

Se deben instalar las Librerías

 En Debian/Ubuntu:

sudo apt-get install libssl-dev libxml2-dev libxmlsec1-dev

 Sistemas basados en RedHat:

sudo yum install openssl-devel libxml2-devel xmlsec1-devel xmlsec1-openssl-devel libtool-ltdl-devel

Se puede utilizar el usuario demo y certificados entregados en ( no van adjuntos en el proyecto)

http://www.transbankdevelopers.cl/?m=sdk
