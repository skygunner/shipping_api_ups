import re
from collections import namedtuple

PackageShape = namedtuple("PackageShape", ["code", "name"])

def debug_print_tree(elem):   
   import xml.etree.ElementTree as etree
   from xml.dom.minidom import parseString
   node = parseString(etree.tostring(elem).replace('\n', ''))
   print(node.toprettyxml(indent="   "))
   
import logging
def setLoggingLevel(level = logging.ERROR):
   """ Convenience function to set all the logging in one place """
   logging.getLogger('%s.ups' % __name__).setLevel(level)
   logging.getLogger('%s.fedex' % __name__).setLevel(level)
   logging.getLogger('%s.endicia' % __name__).setLevel(level)
   logging.getLogger('suds.client').setLevel(level)
   logging.getLogger('suds.transport').setLevel(level)
   logging.getLogger('suds.xsd.schema').setLevel(level)
   logging.getLogger('suds.wsdl').setLevel(level)

class Package(object):
    def __init__(self, weight_in_ozs, length, width, height, mail_class="", value=0, require_signature=False, reference=u''):
        self.weight = weight_in_ozs / 16.0

        # Figure out what is our *true* height, length, and width.
        # Seems like a weird thing to do, but UPS wants it like this.
        dimensions = [length, width, height]
        self.length = max(dimensions)
        self.height = min(dimensions)
        dimensions.remove(height)
        self.width = min(dimensions)
        
        self.value = value
        self.require_signature = require_signature
        self.reference = reference
        self.shape = self._get_shape()
        self.mail_class = mail_class
    
    @property
    def weight_in_ozs(self):
        return self.weight * 16

    @property
    def weight_in_lbs(self):
        return self.weight

    def _get_shape(self):
        # Try to find the smallest package shape we can possibly fit into.
        if self.length < 13 and self.height < 9.5 and self.width < 1:
            return PackageShape('01', 'UPS Letter')

        if self.length < 14.75 and self.height < 11.5 and self.width < 1:
            return PackageShape('04', 'Express PAK')

        if self.length < 13 and self.height < 11 and self.width < 2:
            return PackageShape('2a', 'Small Express Box')

        if self.length < 16 and self.height < 11 and self.width < 3:
            return PackageShape('2b', 'Medium Express Box')

        if self.length < 18 and self.height < 13 and self.width < 3:
            return PackageShape('2c', 'Large Express Box')

        if self.length < 18 and self.height < 12.5 and self.width < 3.75:
            return PackageShape('21', 'UPS Express Box')

        if self.length < 38 and self.height < 7.5 and self.width < 6.5:
            return PackageShape('03', 'Tube')

        return PackageShape('02', 'Custom Packaging')

        
class Product(object):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        

class Address(object):
    def __init__(self, name, address, city, state, zip, country, address2='', phone='', email='', is_residence=True, company_name=''):
        self.company_name = company_name or ''
        self.name = name or ''
        self.address1 = address or ''
        self.address2 = address2 or ''
        self.city = city or ''
        self.state = state or ''
        self.zip = re.sub('[^\w]', '', unicode(zip).split('-')[0]) if zip else ''
        self.country = country or ''
        self.phone = re.sub('[^0-9]*', '', unicode(phone)) if phone else ''
        self.email = email or ''
        self.is_residence = is_residence or False
    
    def __eq__(self, other):
        return vars(self) == vars(other)
    
    def __repr__(self):
        street = self.address1
        if self.address2:
            street += '\n' + self.address2
        return '%s\n%s\n%s, %s %s %s' % (self.name, street, self.city, self.state, self.zip, self.country)

def get_country_code(country):
    lookup = {
        'us': 'US',
        'usa': 'US',
        'united states': 'US',
        'canada': 'CA',
        'ca': 'CA'
    }

    return lookup.get(country.lower(), country)