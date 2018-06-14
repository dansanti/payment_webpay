"""Functions for WS-Security (WSSE) signature creation and verification.

Heavily based on test examples in https://github.com/mehcode/python-xmlsec as
well as the xmlsec documentation at https://www.aleksey.com/xmlsec/.

Reading the xmldsig, xmlenc, and ws-security standards documents, though
admittedly painful, will likely assist in understanding the code in this
module.

"""
from lxml import etree
import xmlsec

from .constants import DS_NS, SOAP_NS, WSSE_NS, WSU_NS
from .exceptions import SignatureVerificationFailed
from .xml import ensure_id, ns

import sys

def sign(envelope, keyfile, certfile):
    """Sign given SOAP envelope with WSSE sig using given key and cert.

    Sign the wsu:Timestamp node in the wsse:Security header and the soap:Body;
    both must be present.

    Add a ds:Signature node in the wsse:Security header containing the
    signature.

    Use EXCL-C14N transforms to normalize the signed XML (so that irrelevant
    whitespace or attribute ordering changes don't invalidate the
    signature). Use SHA1 signatures.

    Expects to sign an incoming document something like this (xmlns attributes
    omitted for readability):

    <soap:Envelope>
      <soap:Header>
        <wsse:Security mustUnderstand="true">
          <wsu:Timestamp>
            <wsu:Created>2015-06-25T21:53:25.246276+00:00</wsu:Created>
            <wsu:Expires>2015-06-25T21:58:25.246276+00:00</wsu:Expires>
          </wsu:Timestamp>
        </wsse:Security>
      </soap:Header>
      <soap:Body>
        ...
      </soap:Body>
    </soap:Envelope>

    After signing, the sample document would look something like this (note the
    added wsu:Id attr on the soap:Body and wsu:Timestamp nodes, and the added
    ds:Signature node in the header, with ds:Reference nodes with URI attribute
    referencing the wsu:Id of the signed nodes):

    <soap:Envelope>
      <soap:Header>
        <wsse:Security mustUnderstand="true">
          <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
            <SignedInfo>
              <CanonicalizationMethod
                  Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
              <SignatureMethod
                  Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>
              <Reference URI="#id-d0f9fd77-f193-471f-8bab-ba9c5afa3e76">
                <Transforms>
                  <Transform
                      Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
                </Transforms>
                <DigestMethod
                    Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>
                <DigestValue>nnjjqTKxwl1hT/2RUsBuszgjTbI=</DigestValue>
              </Reference>
              <Reference URI="#id-7c425ac1-534a-4478-b5fe-6cae0690f08d">
                <Transforms>
                  <Transform
                      Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
                </Transforms>
                <DigestMethod
                    Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>
                <DigestValue>qAATZaSqAr9fta9ApbGrFWDuCCQ=</DigestValue>
              </Reference>
            </SignedInfo>
            <SignatureValue>Hz8jtQb...bOdT6ZdTQ==</SignatureValue>
            <KeyInfo>
              <wsse:SecurityTokenReference>
                <X509Data>
                  <X509Certificate>MIIDnzC...Ia2qKQ==</X509Certificate>
                  <X509IssuerSerial>
                    <X509IssuerName>...</X509IssuerName>
                    <X509SerialNumber>...</X509SerialNumber>
                  </X509IssuerSerial>
                </X509Data>
              </wsse:SecurityTokenReference>
            </KeyInfo>
          </Signature>
          <wsu:Timestamp wsu:Id="id-7c425ac1-534a-4478-b5fe-6cae0690f08d">
            <wsu:Created>2015-06-25T22:00:29.821700+00:00</wsu:Created>
            <wsu:Expires>2015-06-25T22:05:29.821700+00:00</wsu:Expires>
          </wsu:Timestamp>
        </wsse:Security>
      </soap:Header>
      <soap:Body wsu:Id="id-d0f9fd77-f193-471f-8bab-ba9c5afa3e76">
        ...
      </soap:Body>
    </soap:Envelope>

    """
    doc = etree.fromstring(envelope)

    # Create the Signature node.
    signature = xmlsec.template.create(
        doc,
        xmlsec.Transform.EXCL_C14N,
        xmlsec.Transform.RSA_SHA1,
    )

    # Add a KeyInfo node with X509Data child to the Signature. XMLSec will fill
    # in this template with the actual certificate details when it signs.
    key_info = xmlsec.template.ensure_key_info(signature)
    x509_data = xmlsec.template.add_x509_data(key_info)
    x509_issuer_serial = etree.Element(ns(DS_NS, 'X509IssuerSerial'))
    x509_data.append(x509_issuer_serial)
    x509_certificate = etree.Element(ns(DS_NS, 'X509Certificate'))
    x509_data.append(x509_certificate)

    # Load the signing key and certificate.
    key = xmlsec.Key.from_memory(keyfile, xmlsec.KeyFormat.PEM)
    key.load_cert_from_memory(certfile, xmlsec.KeyFormat.PEM)

    # Insert the Signature node in the wsse:Security header.
    header = doc.find(ns(SOAP_NS, 'Header'))
    security = header.find(ns(WSSE_NS, 'Security'))
    security.insert(0, signature)

    # Perform the actual signing.
    ctx = xmlsec.SignatureContext()
    ctx.key = key
    _sign_node(ctx, signature, doc.find(ns(SOAP_NS, 'Body')))
    #_sign_node(ctx, signature, security.find(ns(WSU_NS, 'Timestamp')))
    ctx.sign(signature)

    # Place the X509 data inside a WSSE SecurityTokenReference within
    # KeyInfo. The recipient expects this structure, but we can't rearrange
    # like this until after signing, because otherwise xmlsec won't populate
    # the X509 data (because it doesn't understand WSSE).
    sec_token_ref = etree.SubElement(
        key_info, ns(WSSE_NS, 'SecurityTokenReference'))
    sec_token_ref.append(x509_data)

    return etree.tostring(doc)


def verify(envelope, certfile):
    """Verify WS-Security signature on given SOAP envelope with given cert.

    Expects a document like that found in the sample XML in the ``sign()``
    docstring.

    Raise SignatureValidationFailed on failure, silent on success.

    """
    doc = etree.fromstring(envelope)
    header = doc.find(ns(SOAP_NS, 'Header'))
    security = header.find(ns(WSSE_NS, 'Security'))
    signature = security.find(ns(DS_NS, 'Signature'))

    ctx = xmlsec.SignatureContext()

    # Find each signed element and register its ID with the signing context.
    refs = signature.xpath(
        'ds:SignedInfo/ds:Reference', namespaces={'ds': DS_NS})
    for ref in refs:
        # Get the reference URI and cut off the initial '#'
        referenced_id = ref.get('URI')[1:]
        referenced = doc.xpath(
            "//*[@wsu:Id='%s']" % referenced_id,
            namespaces={'wsu': WSU_NS},
        )[0]
        ctx.register_id(referenced, 'Id', WSU_NS)

    try :
 	key = xmlsec.Key.from_memory(certfile, xmlsec.KeyFormat.CERT_PEM, None)
	ctx.key = key
    except :
	sys.exit()

    try:
        ctx.verify(signature)
    except xmlsec.Error:
        # Sadly xmlsec gives us no details about the reason for the failure, so
        # we have nothing to pass on except that verification failed.
        raise SignatureVerificationFailed()


def _sign_node(ctx, signature, target):
    """Add sig for ``target`` in ``signature`` node, using ``ctx`` context.

    Doesn't actually perform the signing; ``ctx.sign(signature)`` should be
    called later to do that.

    Adds a Reference node to the signature with URI attribute pointing to the
    target node, and registers the target node's ID so XMLSec will be able to
    find the target node by ID when it signs.

    """
    # Ensure the target node has a wsu:Id attribute and get its value.
    node_id = ensure_id(target)
    # Add reference to signature with URI attribute pointing to that ID.
    ref = xmlsec.template.add_reference(
        signature, xmlsec.Transform.SHA1, uri='#' + node_id)
    # This is an XML normalization transform which will be performed on the
    # target node contents before signing. This ensures that changes to
    # irrelevant whitespace, attribute ordering, etc won't invalidate the
    # signature.
    xmlsec.template.add_transform(ref, xmlsec.Transform.EXCL_C14N)
    # Unlike HTML, XML doesn't have a single standardized Id. WSSE suggests the
    # use of the wsu:Id attribute for this purpose, but XMLSec doesn't
    # understand that natively. So for XMLSec to be able to find the referenced
    # node by id, we have to tell xmlsec about it using the register_id method.
    ctx.register_id(target, 'Id', WSU_NS)
