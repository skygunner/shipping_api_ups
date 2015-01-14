"""
Defines public methods and classes for other modules to use.
Breaking changes are never introduced within a version.

"""
from openerp import pooler
from ...helpers import ups, shipping, settings, label

def get_config(cr, uid, sale=None, logistic_company_id=None, context=None, config=None):
    """Returns the UPS configuration relevant to the given object."""

    if not config and sale and sale.ups_shipper_id:
        config = sale.ups_shipper_id

    if not config and logistic_company_id:
        log_comp = pooler.get_pool('logistic.company').browse(cr, uid, logistic_company_id, context=context)
        config = log_comp.ups_account_shipping_id if log_comp else None

    if not config and sale:
        config = sale.company_id.ups_account_shipping_id

    if not config:
        # Just go by uid.
        user_pool = pooler.get_pool(cr.dbname).get("res.users")
        user = user_pool.browse(cr, uid, uid, context=context)
        config = user.company_id.ups_account_shipping_id

    if config:
        return {
            'username': config.userid,
            'password': config.password,
            'access_license': config.access_license,
            'shipper_number': config.acc_no,
            "sandbox": config.sandbox,
            "negotiated_rates": config.negotiated_rates
        }

    return settings.UPS_CONFIG
    
def get_quotes(config, package, sale=None, from_address=None, to_address=None, test=None):
    """Calculates the cost of shipping for all USPS's services."""

    # Get the shipper and recipient addresses for this order.
    if sale:
        from_address = sale.company_id.partner_id
        to_address = sale.partner_shipping_id or ''
        from_address.state = from_address.state_id.code
        from_address.country = from_address.country_id.name
        to_address.state = to_address.state_id.code
        to_address.country = to_address.country_id.name

    shipper = shipping.Address(
        name=from_address.name, address=from_address.street,
        address2=from_address.street2, city=from_address.city,
        state=from_address.state_id.code, zip=from_address.zip,
        country=from_address.country_id.code
    )

    recipient = shipping.Address(
        name=to_address.name, address=to_address.street,
        address2=to_address.street2, city=to_address.city,
        state=to_address.state_id.code, zip=to_address.zip,
        country=to_address.country_id.code
    )

    if sale.ups_shipper_id:
        test = sale.ups_shipper_id.sandbox

    test = config["sandbox"] if test == None else test

    # Set up our API client, get our rates, and construct our return value.
    api = ups.UPS(config, debug=test)

    ups_package = shipping.Package(
        package.weight, package.length, package.width, package.height
    )

    response = api.rate(ups_package, shipper, recipient)

    return [
        {"company": "UPS", "container": item["package"], "service": item['service'], "price": item["cost"]}
        for item in response['info']
    ]


def get_label(config, package, service, picking=None, from_address=None, to_address=None, customs=None, test=None,
              image_format="EPL2"):
    if test == None:
        test = config["sandbox"]

    try:
        return label.Label(package, picking=picking, from_address=from_address, to_address=to_address,
                           customs=customs, config=config, test=test
        ).get(service, image_format=image_format)
    except Exception as e:
        return {"success": False, "error": str(e)}


def cancel_shipping(config, packages, test=None):
    if test == None:
        test = config["sandbox"]

    api = ups.UPS(config, debug=test)
    return api.cancel(packages)