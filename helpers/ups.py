import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

import os
import urllib2
import datetime
import base64
import xml.etree.ElementTree as etree
from collections import namedtuple
from shipping import Package, get_country_code
from mako.lookup import TemplateLookup

SERVICES = [
    ('03', 'UPS Ground'),
    ('11', 'UPS Standard'),
    ('01', 'UPS Next Day'),
    ('14', 'UPS Next Day AM'),
    ('13', 'UPS Next Day Air Saver'),
    ('02', 'UPS 2nd Day'),
    ('59', 'UPS 2nd Day AM'),
    ('12', 'UPS 3-day Select'),
    ('65', 'UPS Saver'),
    ('07', 'UPS Worldwide Express'),
    ('08', 'UPS Worldwide Expedited'),
    ('54', 'UPS Worldwide Express Plus'),
    ('96', 'UPS Worldwide Express Freight'),
]

PACKAGES = [
    ('02', 'Custom Packaging'),
    ('01', 'UPS Letter'),
    ('03', 'Tube'),
    ('04', 'PAK'),
    ('21', 'UPS Express Box'),
    ('2a', 'Small Express Box'),
    ('2b', 'Medium Express Box'),
    ('2c', 'Large Express Box'),
]

LABEL_TYPE = [
	('GIF', 'GIF Format'),
	('ZPL','Zebra Label Printer Format')
]

Label = namedtuple("Label", ["shipment_id", "tracking", "postage", "label", "format"])

class UPSError(Exception):
    pass
        
class UPS(object):
    def __init__(self, credentials, debug=True):
        this_dir = os.path.dirname(os.path.realpath(__file__))
        self.templates = TemplateLookup(directories=[os.path.join(this_dir, 'ups')], default_filters=['unicode', 'x'])
        self.credentials = credentials
        self.debug = debug
        domain = 'wwwcie.ups.com' if self.debug else 'onlinetools.ups.com'
        self.endpoints = {
            "rate": "https://%s/ups.app/xml/Rate" % domain,
            'confirm': "https://%s/ups.app/xml/ShipConfirm" % domain,
            'accept': "https://%s/ups.app/xml/ShipAccept" % domain,
            'cancel': "https://%s/ups.app/xml/Void" % domain
        }

    def rate(self, package, shipper, recipient, insurance='OFF', insurance_amount=0, delivery_confirmation=False, signature_confirmation=False):
        services = dict(SERVICES)

        # Play nice with the other function signatures, which expect to take lists of packages.
        if not isinstance(package, Package):

            # But not too nice.
            if len(package) > 1:
                raise Exception("Can only take one Package at a time!")

            package = package[0]

        shipper.country_code = get_country_code(shipper.country)
        recipient.country_code = get_country_code(recipient.country)
        data = self.templates.get_template("RatingServiceSelectionRequest.mko").render(
                credentials=self.credentials, shipper=shipper, recipient=recipient, package=package
        )

        try:
            httpresq = urllib2.Request(url=self.endpoints["rate"], data=data.encode('utf_8'),
                                       headers={'Content-Type': 'application/x-www-form-urlencoded'})
            reply = etree.fromstring(urllib2.urlopen(httpresq).read())
            response = { 'status': reply.find('Response/ResponseStatusDescription').text, 'info': list() }
            error = reply.find('Response/Error')

            if error is not None:
                #error_location = error.find("ErrorLocation")
                #error_xpath = error.find("ErrorLocationElementName")
                response["error"] = error.find("ErrorDescription").text

                #if error_location:
                #    response["error_location"] = error_location.text

                #if error_xpath:
                #    response["error_xpath"] = error_xpath.text

                raise UPSError(response["error"])

            for details in reply.findall('RatedShipment'):
                service_code = details.find('Service/Code').text
                response['info'].append({
                    'service': services.get(service_code, service_code),
                    'package': package.shape.name,
                    'delivery_day': '',
                    'cost': float(details.find('TotalCharges/MonetaryValue').text)
                })
            return response

        except urllib2.URLError as e:
            raise UPSError(e)


    def label(self, package, shipper, recipient, customs=None, image_format="EPL2"):
        shipper.country_code = get_country_code(shipper.country)
        recipient.country_code = get_country_code(recipient.country)
        invoice_date = datetime.date.today().strftime('%Y%m%d')
        data = self.templates.get_template("ShipmentConfirmRequest.mko").render(
                credentials=self.credentials, shipper=shipper, recipient=recipient,
                package=package, invoice_date=invoice_date, customs=customs,
                image_format=image_format
        )

        httpresq = urllib2.Request(url=self.endpoints["confirm"], data=data.encode('utf_8'),
                                   headers={'Content-Type': 'application/x-www-form-urlencoded'})

        reply = etree.fromstring(urllib2.urlopen(httpresq).read())
        response = { 'status': reply.find('Response/ResponseStatusDescription').text, 'info': list() }
        error = reply.find('Response/Error')

        if error:
            error_location = error.find("ErrorLocation")
            error_xpath = error_location.find("ErrorLocationElementName") if error_location else error.find("ErrorLocationElementName")
            response["error"] = error.find("ErrorDescription").text

            if error_location:
                response["error_location"] = error_location.text

            if error_xpath:
                response["error_xpath"] = error_xpath.text

            return response

        data = self.templates.get_template("ShipmentAcceptRequest.mko").render(
                credentials=self.credentials, digest=reply.find('ShipmentDigest').text
        )

        httpresq = urllib2.Request(url=self.endpoints["accept"], data=data.encode('utf_8'),
                                   headers={'Content-Type': 'application/x-www-form-urlencoded'})

        reply = etree.fromstring(urllib2.urlopen(httpresq).read())
        error = reply.find('Response/Error')

        if error:
            response = {}
            error_location = error.find("ErrorLocation")
            error_xpath = error.find("ErrorLocationElementName")
            response["error"] = error.find("ErrorDescription").text

            if error_location:
                response["error_location"] = error_location.text

            if error_xpath:
                response["error_xpath"] = error_xpath.text

            return response

        shipment = reply.find("ShipmentResults")
        label = Label(
            postage=shipment.find("ShipmentCharges/TotalCharges/MonetaryValue").text,
            shipment_id=shipment.find("ShipmentIdentificationNumber").text,
            tracking=shipment.find("PackageResults/TrackingNumber").text,
            label=[base64.b64decode(shipment.find("PackageResults/LabelImage/GraphicImage").text)],
            format=[shipment.find("PackageResults/LabelImage/LabelImageFormat/Code").text]
        )

        # UPS truncates EPL2 to EPL.
        if label.format == "EPL":
            label.format = "EPL2"

        return label

    def cancel(self, packages):
        services = dict(SERVICES)

        if not packages:
            return {"error": "No packages specified!"}

        data = self.templates.get_template("VoidShipmentRequest.mko").render(
                credentials=self.credentials, packages=packages
        )
        print data

        try:
            httpresq = urllib2.Request(url=self.endpoints["cancel"], data=data.encode('utf_8'),
                                       headers={'Content-Type': 'application/x-www-form-urlencoded'})
            reply = etree.fromstring(urllib2.urlopen(httpresq).read())
            response = {'status': reply.find('Response/ResponseStatusDescription').text, 'info': list()}
            error = reply.find('Response/Error')

            if error is not None:
                #error_location = error.find("ErrorLocation")
                #error_xpath = error.find("ErrorLocationElementName")
                response["error"] = error.find("ErrorDescription").text

                #if error_location:
                #    response["error_location"] = error_location.text

                #if error_xpath:
                #    response["error_xpath"] = error_xpath.text

                raise UPSError(response["error"])

            return response

        except urllib2.URLError as e:
            raise UPSError(e)
