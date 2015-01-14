import os
import math
import pickle
import settings
from ups import UPS
from shipping import Package, Address

class Label(object):

    def __init__(self, pkg, picking=None, from_address=None, to_address=None, customs=None, config=None, test=None):
        self.pkg = pkg
        self.picking = picking
        self.customs = customs

        if config == None:
            config = settings.UPS_CONFIG

        # Are we running in test mode? If so, we'll
        # need to use UPS's sandbox servers.
        if picking and picking.logis_company and test == None:
            test = picking.logis_company.test_mode

        self.api = UPS(config, debug=(test if test != None else False))

        # Get the shipper and recipient addresses for this order.
        if picking and not from_address:
            from_address = picking.company_id.partner_id
            from_address.state = from_address.state_id.code
            from_address.country = from_address.country_id.name

        if picking and not to_address:
            to_address = picking.partner_id or ''
            to_address.state = to_address.state_id.code
            to_address.country = to_address.country_id.name

        # Create the Address objects that we'll later pass to our Endicia object.
        self.shipper = Address(
            from_address.name, from_address.street, from_address.city, from_address.state,
            from_address.zip, from_address.country, address2=from_address.street2,
            phone=from_address.phone
        )
        self.recipient = Address(
            to_address.name, to_address.street, to_address.city, to_address.state,
            to_address.zip, to_address.country, address2=to_address.street2,
            phone=to_address.phone
        )


    def from_cache(self, service, image_format="EPL2"):
        ext = image_format.lower()
        label_dir = os.path.dirname(os.path.realpath(__file__)) + '/../labels' + '/%s' % self.picking.id

        if not os.path.exists(label_dir):
            os.makedirs(label_dir)

        label_filename = label_dir + "%s.%s" % (self.pkg.id, ext)

        if os.path.exists(label_filename):
            # Load the shipping label from storage.
            label_file = open(label_filename, 'r')
            label = pickle.load(label_file)
            label_file.close()

        else:
            # Get the shipping label and store it.
            label = self.generate(service, image_format=image_format)
            label_file = open(label_dir + "/%s.%s" % (self.pkg.id, ext), 'w')
            pickle.dump(label, label_file)
            label_file.close()

        return label


    def get(self, service, image_format="EPL2"):
        '''Generate or retrieve the shipping label for the given package.'''

        if self.picking: # Is this a cachable label?
            label = self.from_cache(service, image_format=image_format)
        else:
            label = self.generate(service, image_format=image_format)

        return label


    def generate(self, service, image_format="EPL2"):
        if service == None and self.picking:
            service = self.picking.usps_service_type

        weight = math.modf(self.pkg.weight)
        ounces = (weight[1] * 16) + round(weight[0] * 16, 2)

        package = Package(
            ounces, self.pkg.height, self.pkg.length, self.pkg.width, mail_class=service, value=self.pkg.value)

        label = self.api.label(package, self.shipper, self.recipient, customs=self.customs, image_format=image_format)

        if hasattr(label, 'label'):
            return label

        raise Exception(label.get("error", "Could not generate UPS label!"))