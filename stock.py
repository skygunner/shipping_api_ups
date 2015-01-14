# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2011 NovaPoint Group LLC (<http://www.novapointgroup.com>)
#    Copyright (C) 2004-2010 OpenERP SA (<http://www.openerp.com>)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
#
##############################################################################


import base64
import time
import datetime
import Image
import tempfile
import httplib
from urlparse import urlparse
import logging
import tools
from tools.translate import _
from openerp.osv import fields, osv
import os
from . import api

class shipping_move(osv.osv):
    
    _inherit = "shipping.move"
    _columns = {
        'shipment_identific_no': fields.char('ShipmentIdentificationNumber', size=64,),
        'logo': fields.binary('Logo'),
        'tracking_url': fields.char('Tracking URL', size=512,),
        'service': fields.many2one('ups.shipping.service.type', 'Shipping Service'),
        'shipper': fields.many2one('ups.account.shipping', 'Shipper', help='The specific user ID and shipper. Setup in the company configuration.'),
        }
    
    def print_label(self, cr, uid, ids, context=None):
        if not ids: return []

        return {
            'type': 'ir.actions.report.xml',
            'report_name': 'ship.log.label.print',
            'datas': {
                'model':'shipping.move',
                'id': ids and ids[0] or False,
                'ids': ids and ids or [],
                'report_type': 'pdf'
                },
            'nodestroy': True
        }

    def getTrackingUrl(self, cr, uid, ids, context=None):
        ship_log_obj = self.browse(cr, uid, ids[0], context=context)
        if ship_log_obj.tracking_no:
            tracking_url = "http://wwwapps.ups.com/WebTracking/processInputRequest?sort_by=status&tracknums_displayed=1&\
                            TypeOfInquiryNumber=T&loc=en_US&InquiryNumber1=%s&track.x=0&track.y=0" % ship_log_obj.tracking_no

shipping_move()

class stock_picking(osv.osv):
    
    _inherit = "stock.picking"
    
    def _get_company_code(self, cr, user, context=None):
        res = super(stock_picking, self)._get_company_code(cr, user, context=context)
        res.append(('ups', 'UPS'))
        return list(set(res))
    
    
    _columns = {
        'ups_service': fields.many2one('ups.shipping.service.type', 'Service', help='The specific shipping service offered'),
        'shipper': fields.many2one('ups.account.shipping', 'Shipper', help='The specific user ID and shipper. Setup in the company configuration.'),
        'shipment_digest': fields.text('ShipmentDigest'),
        'negotiated_rates': fields.float('NegotiatedRates'),
        'shipment_identific_no': fields.char('ShipmentIdentificationNumber', size=64,),
        'tracking_no': fields.char('TrackingNumber', size=64,),
        'trade_mark': fields.related('shipper', 'trademark', type='char', size=1024, string='Trademark'),
        'ship_company_code': fields.selection(_get_company_code, 'Ship Company', method=True, size=64),
        'ups_pickup_type': fields.selection([
            ('01', 'Daily Pickup'),
            ('03', 'Customer Counter'),
            ('06', 'One Time Pickup'),
            ('07', 'On Call Air'),
            ('11', 'Suggested Retail Rates'),
            ('19', 'Letter Center'),
            ('20', 'Air Service Center'),
            ], 'Pickup Type'),
        'ups_packaging_type': fields.many2one('shipping.package.type', 'Packaging Type'),
        'ups_use_cc': fields.boolean('Credit Card Payment'),
        'ups_cc_type': fields.selection([
            ('01', 'American Express'),
            ('03', 'Discover'),
            ('04', 'MasterCard'),
            ('05', 'Optima'),
            ('06', 'VISA'),
            ('07', 'Bravo'),
            ('08', 'Diners Club')
            ], 'Card Type'),
        'ups_cc_number': fields.char('Credit Card Number', size=32),
        'ups_cc_expiaration_date': fields.char('Expiaration Date', size=6, help="Format is 'MMYYYY'"),
        'ups_cc_security_code': fields.char('Security Code', size=4,),
        'ups_cc_address_id': fields.many2one('res.partner', 'Address'),
        'ups_third_party_account': fields.char('Third Party Account Number', size=32),
        'ups_third_party_address_id': fields.many2one('res.partner', 'Third Party Address'),
        'ups_third_party_type': fields.selection([('shipper', 'Shipper'), ('consignee', 'Consignee')], 'Third Party Type'),
        'ups_bill_receiver_account': fields.char('Receiver Account', size=32, help="The UPS account number of Freight Collect"),
        'ups_bill_receiver_address_id': fields.many2one('res.partner', 'Receiver Address')
    }
    
    def on_change_sale_id(self, cr, uid, ids, sale_id=False, state=False, context=None):
        vals = {}
        if sale_id:
            sale_obj = self.pool.get('sale.order').browse(cr, uid, sale_id)
            service_type_obj = self.pool.get('ups.shipping.service.type')
            ups_shipping_service_ids = service_type_obj.search(cr, uid, [('description', '=', sale_obj.ship_method_id.name)], context=context)
            if ups_shipping_service_ids:
                vals['ups_service'] = ups_shipping_service_ids[0]
                shipping_obj = self.pool.get('ups.account.shipping')
                ups_shipping_ids = shipping_obj.search(cr, uid, [('ups_shipping_service_ids', 'in', ups_shipping_service_ids[0])], context=context)
                if ups_shipping_ids:
                    vals['shipper'] = ups_shipping_ids[0]
                    log_company_obj = self.pool.get('logistic.company')
                    logistic_company_ids = log_company_obj.search(cr, uid, [('ups_account_shipping_ids', 'in', ups_shipping_ids[0])], context=context)
                    if logistic_company_ids:
                        vals['logis_company'] = logistic_company_ids[0]
        return {'value': vals}
    
    def onchange_bill_shipping(self, cr, uid, ids, bill_shipping, ups_use_cc, ups_cc_address_id, ups_bill_receiver_address_id, partner_id,
                               shipper, context=None):
        vals = {}
        if bill_shipping == 'shipper':
            if not ups_cc_address_id and shipper:
                ship_address = self.pool.get('ups.account.shipping').read(cr, uid, shipper, ['address'], context=context)['address']
                if ship_address:
                    vals['ups_cc_address_id'] = ship_address[0]
        else:
            vals['ups_use_cc'] = False
        if not ups_bill_receiver_address_id:
            vals['ups_bill_receiver_address_id'] = partner_id
        return {'value' : vals}

stock_picking()

class stock_picking_out(osv.osv):
    _inherit = "stock.picking.out"

    def _get_company_code(self, cr, user, context=None):
        return self.pool.get('stock.picking')._get_company_code(cr, user, context)
    

    _columns = {
        'ups_service': fields.many2one('ups.shipping.service.type', 'Service', help='The specific shipping service offered'),
        'shipper': fields.many2one('ups.account.shipping', 'Shipper', help='The specific user ID and shipper. Setup in the company configuration.'),
        'shipment_digest': fields.text('ShipmentDigest'),
        'negotiated_rates': fields.float('NegotiatedRates'),
        'shipment_identific_no': fields.char('ShipmentIdentificationNumber', size=64,),
        'tracking_no': fields.char('TrackingNumber', size=64,),
        'trade_mark': fields.related('shipper', 'trademark', type='char', size=1024, string='Trademark'),
        'ship_company_code': fields.selection(_get_company_code, 'Ship Company', method=True, size=64),
        'ups_pickup_type': fields.selection([
            ('01', 'Daily Pickup'),
            ('03', 'Customer Counter'),
            ('06', 'One Time Pickup'),
            ('07', 'On Call Air'),
            ('11', 'Suggested Retail Rates'),
            ('19', 'Letter Center'),
            ('20', 'Air Service Center'),
            ], 'Pickup Type'),
        'ups_packaging_type': fields.many2one('shipping.package.type', 'Packaging Type'),
        'ups_use_cc': fields.boolean('Credit Card Payment'),
        'ups_cc_type': fields.selection([
            ('01', 'American Express'),
            ('03', 'Discover'),
            ('04', 'MasterCard'),
            ('05', 'Optima'),
            ('06', 'VISA'),
            ('07', 'Bravo'),
            ('08', 'Diners Club')
            ], 'Card Type'),
        'ups_cc_number': fields.char('Credit Card Number', size=32),
        'ups_cc_expiaration_date': fields.char('Expiaration Date', size=6, help="Format is 'MMYYYY'"),
        'ups_cc_security_code': fields.char('Security Code', size=4,),
        'ups_cc_address_id': fields.many2one('res.partner', 'Address'),
        'ups_third_party_account': fields.char('Third Party Account Number', size=32),
        'ups_third_party_address_id': fields.many2one('res.partner', 'Third Party Address'),
        'ups_third_party_type': fields.selection([('shipper', 'Shipper'), ('consignee', 'Consignee')], 'Third Party Type'),
        'ups_bill_receiver_account': fields.char('Receiver Account', size=32, help="The UPS account number of Freight Collect"),
        'ups_bill_receiver_address_id': fields.many2one('res.partner', 'Receiver Address')
        }

    def onchange_bill_shipping(self, cr, uid, ids, bill_shipping, ups_use_cc, ups_cc_address_id, ups_bill_receiver_address_id, partner_id,
                               shipper, context=None):
        vals = {}
        if bill_shipping == 'shipper':
            if not ups_cc_address_id and shipper:
                ship_address = self.pool.get('ups.account.shipping').read(cr, uid, shipper, ['address'], context=context)['address']
                if ship_address:
                    vals['ups_cc_address_id'] = ship_address[0]
        else:
            vals['ups_use_cc'] = False
        if not ups_bill_receiver_address_id:
            vals['ups_bill_receiver_address_id'] = partner_id
        return {'value' : vals}

#     def action_process(self, cr, uid, ids, context=None):
#         sale_order_line = []
#         deliv_order = self.browse(cr, uid, ids, context=context)
#         if isinstance(deliv_order, list):
#             deliv_order = deliv_order[0]
#         do_transaction = True
#         sale = deliv_order.sale_id
#         if sale and sale.payment_method == 'cc_pre_auth' and not sale.invoiced:
#             rel_voucher = sale.rel_account_voucher_id
#             rel_voucher_id = rel_voucher and rel_voucher.id or False
#             if rel_voucher_id and rel_voucher.state != 'posted' and rel_voucher.cc_auth_code:
#                 do_transaction = False
#                 vals_vouch = {'cc_p_authorize': False, 'cc_charge': True}
#                 if 'trans_type' in rel_voucher._columns.keys():
#                     vals_vouch.update({'trans_type': 'AuthCapture'})
#                 self.pool.get('account.voucher').write(cr, uid, [rel_voucher_id], vals_vouch, context=context)
#                 do_transaction = self.pool.get('account.voucher').authorize(cr, uid, [rel_voucher_id], context=context)
#         if not do_transaction:
#             self.write(cr, uid, ids, {'ship_state': 'hold', 'ship_message': 'Unable to process creditcard payment.'})
#             cr.commit()
#             raise osv.except_osv(_('Final credit card charge cannot be completed!'), _("Please hold shipment and contact customer service.."))
#         return super(stock_picking_out, self).action_process(cr, uid, ids, context=context)
   


    def action_done(self, cr, uid, ids, context=None):
        res = super(stock_picking_out, self).action_done(cr, uid, ids, context=context)

        for picking in self.browse(cr, uid, ids, context=context):
            vals = {}
            service_type_obj = self.pool.get('ups.shipping.service.type')
            ship_method_id = picking.sale_id and picking.sale_id.ship_method_id
            if ship_method_id:
                service_type_ids = service_type_obj.search(cr, uid, [('description', 'like', ship_method_id.name)], context=context)
                if service_type_ids:
                  vals['ups_service'] = service_type_ids[0]
                  service_type = service_type_obj.browse(cr, uid, service_type_ids[0], context=context)
                  if service_type.ups_account_id:
                    vals['shipper'] = service_type.ups_account_id.id
                    if service_type.ups_account_id.logistic_company_id:
                        vals['logis_company'] = service_type_obj.ups_account_id.logistic_company_id.id
        return True
    
    def on_change_sale_id(self, cr, uid, ids, sale_id=False, state=False, context=None):
        vals = {}
        if sale_id:
            sale_obj = self.pool.get('sale.order').browse(cr, uid, sale_id)
            service_type_obj = self.pool.get('ups.shipping.service.type')
            ups_shipping_service_ids = service_type_obj.search(cr, uid, [('description', '=', sale_obj.ship_method_id.name)], context=context)
            if ups_shipping_service_ids:
                vals['ups_service'] = ups_shipping_service_ids[0]
                shipping_obj = self.pool.get('ups.account.shipping')
                ups_shipping_ids = shipping_obj.search(cr, uid, [('ups_shipping_service_ids', 'in', ups_shipping_service_ids[0])], context=context)
                if ups_shipping_ids:
                    vals['shipper'] = ups_shipping_ids[0]
                    log_company_obj = self.pool.get('logistic.company')
                    logistic_company_ids = log_company_obj.search(cr, uid, [('ups_account_shipping_ids', 'in', ups_shipping_ids[0])], context=context)
                    if logistic_company_ids:
                        vals['logis_company'] = logistic_company_ids[0]
        return {'value': vals}

    def fill_addr(self, addr_id):
        ret = {
            'AddressLine1': addr_id and addr_id.street or '',
            'AddressLine2': addr_id and addr_id.street2 or '',
            'AddressLine3': "",
            'City': addr_id and addr_id.city or '',
            'StateProvinceCode': addr_id and addr_id.state_id.id and addr_id.state_id.code or '',
            'PostalCode': addr_id and addr_id.zip or '',
            'CountryCode': addr_id and addr_id.country_id.id and addr_id.country_id.code or '',
            'PostalCode': addr_id.zip or ''
        }
        if addr_id and addr_id.classification == '2':
            ret.update({'ResidentialAddress': ""})
        return ret

    def create_ship_accept_request_new(self, cr, uid, do, context=None):
        if not do.shipper:
            return ''
 
        xml_ship_accept_request = """<?xml version="1.0"?>
            <AccessRequest xml:lang='en-US'>
                <AccessLicenseNumber>%(access_l_no)s</AccessLicenseNumber>
                <UserId>%(user_id)s</UserId>
                <Password>%(password)s</Password>
            </AccessRequest>
            """ % {
                'access_l_no': do.shipper.access_license or '',
                'user_id': do.shipper.userid or '',
                'password': do.shipper.password,
            }
 
        xml_ship_accept_request += """<?xml version="1.0"?>
            <ShipmentAcceptRequest>
                <Request>
                    <TransactionReference>
                        <CustomerContext>%(customer_context)s</CustomerContext>
                        <XpciVersion>1.0001</XpciVersion>
                    </TransactionReference>
                    <RequestAction>ShipAccept</RequestAction>
                </Request>
                <ShipmentDigest>%(shipment_digest)s</ShipmentDigest>
            </ShipmentAcceptRequest>
            """ % {
                'customer_context': do.name or '',
                'shipment_digest': do.shipment_digest,
            }
             
        return xml_ship_accept_request
# 
    def process_ship_accept(self, cr, uid, do, packages, context=None):
        shipment_accept_request_xml = self.create_ship_accept_request_new(cr, uid, do, context=context)
        if do.logis_company.test_mode:
            acce_web = do.logis_company.ship_accpt_test_web or ''
            acce_port = do.logis_company.ship_accpt_test_port
        else:
            acce_web = do.logis_company.ship_accpt_web or ''
            acce_port = do.logis_company.ship_accpt_port
        if acce_web:
            parse_url = urlparse(acce_web)
            serv = parse_url.netloc
            serv_path = parse_url.path
        else:
            raise osv.except_osv(_('Unable to find Shipping URL!'), _("Please configure the shipping company with websites."))
 
        conn = httplib.HTTPSConnection(serv, acce_port)
        res = conn.request("POST", serv_path, shipment_accept_request_xml)
        import xml2dic
        res = conn.getresponse()
        result = res.read()
 
        response_dic = xml2dic.main(result)
        NegotiatedRates = ''
        ShipmentIdentificationNumber = ''
        TrackingNumber = ''
        label_image = ''
        control_log_image = ''
        status = 0
         
        status_description = ''
        for response in response_dic['ShipmentAcceptResponse']:
            if response.get('Response'):
                for resp_items in response['Response']:
                    if resp_items.get('ResponseStatusCode') and resp_items['ResponseStatusCode'] == '1':
                        status = 1
                    if resp_items.get('ResponseStatusDescription'):
                        status_description = resp_items['ResponseStatusDescription']
                    if resp_items.get('Error'):
                        for err in resp_items['Error']:
                            if err.get('ErrorSeverity'):
                                status_description += '\n' + err.get('ErrorSeverity')
                            if err.get('ErrorDescription'):
                                status_description += '\n' + err.get('ErrorDescription')
            do.write({'ship_message': status_description})
            
        packages_ids = [package.id for package in do.packages_ids]
         
        if status:
            shipment_identific_number, tracking_number_notes, ship_charge = '', '', 0.0
            for shipmentresult in response_dic['ShipmentAcceptResponse']:
                if shipmentresult.get('ShipmentResults'):
                    package_obj = self.pool.get('stock.packages')
                    for package in response['ShipmentResults']:
                        if package.get('ShipmentIdentificationNumber'):
                            shipment_identific_number = package['ShipmentIdentificationNumber']
                            continue
                        ship_charge += package.get('ShipmentCharges') and float(package['ShipmentCharges'][2]['TotalCharges'][1]['MonetaryValue']) or 0.0
                        if package.get('PackageResults'):
                            label_image = ''
                            tracking_number = ''
                            label_code = ''
                            tracking_url = do.logis_company.ship_tracking_url or ''
                            for tracks in package['PackageResults']:
                                if tracks.get('TrackingNumber'):
                                    tracking_number = tracks['TrackingNumber']
                                    if tracking_url:
                                        try:
                                            tracking_url = tracking_url % tracking_number
                                        except Exception, e:
                                            tracking_url = "Invalid tracking url on shipping company"
                                if tracks.get('LabelImage'):
                                    for label in tracks['LabelImage']:
                                        if label.get('LabelImageFormat'):
                                            for format in label['LabelImageFormat']:
                                                label_code = format.get('Code')
                                        if label.get('GraphicImage'):
                                            label_image = label['GraphicImage']
                                            im_in_raw = base64.decodestring(label_image)
                                            path = tempfile.mktemp('.txt')
                                            temp = file(path, 'wb')
                                            temp.write(im_in_raw)
                                            result = base64.b64encode(im_in_raw)
                                            (dirName, fileName) = os.path.split(path)
                                            self.pool.get('ir.attachment').create(cr, uid,
                                                      {
                                                       'name': fileName,
                                                       'datas': result,
                                                       'datas_fname': fileName,
                                                       'res_model': self._name,
                                                       'res_id': do.id,
                                                       'type': 'binary'
                                                      },
                                                      context=context)
                                            temp.close()
                                            try:
                                                new_im = Image.open(path)
                                                new_im = new_im.rotate(270)
                                                new_im.save(path, 'JPEG')
                                            except Exception, e:
                                                pass
                                            label_from_file = open(path, 'rb')
                                            label_image = base64.encodestring(label_from_file.read())
                                            label_from_file.close()
                                            if label_code == 'GIF':
                                                package_obj.write(cr, uid, packages_ids[packages], {
                                                    'tracking_no': tracking_number,
                                                    'shipment_identific_no': shipment_identific_number,
                                                    'logo': label_image,
                                                    'ship_state': 'in_process',
                                                    'tracking_url': tracking_url,
                                                    'att_file_name': fileName
                                                    
                                                    }, context=context)
                                            else:
                                                package_obj.write(cr, uid, packages_ids[packages], {
                                                    'tracking_no': tracking_number,
                                                    'shipment_identific_no': shipment_identific_number,
                                                    'ship_state': 'in_process',
                                                    'tracking_url': tracking_url,
                                                    'att_file_name': fileName
                                                    }, context=context)
                                                 
                                            if int(time.strftime("%w")) in range(1, 6) or (time.strftime("%w") == '6' and do.sat_delivery):
                                                next_pic_date = time.strftime("%Y-%m-%d")
                                            else:
                                                timedelta = datetime.timedelta(7 - int(time.strftime("%w")))
                                                next_pic_date = (datetime.datetime.today() + timedelta).strftime("%Y-%m-%d")
                                             
                                            package_data = package_obj.read(cr, uid, packages_ids[packages], ['weight', 'description'], context=context)
#                                             i += 1
                                            ship_move_obj = self.pool.get('shipping.move')
                                            if label_code == 'GIF':
                                                ship_move_obj.create(cr, uid, {
                                                    'pick_id': do.id,
                                                    'package_weight': package_data['weight'],
                                                    'partner_id': do.partner_id.id,
                                                    'service': do.ups_service.id,
                                                    'ship_to': do.partner_id.id,
                                                    'ship_from': do.ship_from and do.ship_from_address.id  or \
                                                                 do.shipper and do.shipper.address and do.shipper.address.id,
                                                    'tracking_no': tracking_number,
                                                    'shipment_identific_no': shipment_identific_number,
                                                    'logo': label_image,
                                                    'state': 'ready_pick',
                                                    'tracking_url': tracking_url,
                                                    'package': package_data['description'] and str(package_data['description'])[:126],
                                                    'pic_date': next_pic_date,
                                                    'sale_id': do.sale_id.id and do.sale_id.id or False,
                                                    }, context=context)
                                            else:
                                                ship_move_obj.create(cr, uid, {
                                                    'pick_id': do.id,
                                                    'package_weight': package_data['weight'],
                                                    'partner_id': do.partner_id.id,
                                                    'service': do.ups_service.id,
                                                    'ship_to': do.partner_id.id,
                                                    'ship_from': do.ship_from and do.ship_from_address.id  or \
                                                                 do.shipper and do.shipper.address and do.shipper.address.id,
                                                    'tracking_no': tracking_number,
                                                    'shipment_identific_no': shipment_identific_number,
                                                    'state': 'ready_pick',
                                                    'tracking_url': tracking_url,
                                                    'package': package_data['description'] and str(package_data['description'])[:126],
                                                    'pic_date': next_pic_date,
                                                    'sale_id': do.sale_id.id and do.sale_id.id or False,
                                                    }, context=context)
                                            tracking_number_notes += '\n' + tracking_number
                                            
                        if package.get('ControlLogReceipt'):
                            for items in package['ControlLogReceipt']:
                                if items.get('GraphicImage'):
                                    control_log_image = items['GraphicImage']
                                    im_in_raw = base64.decodestring(control_log_image)
                                    file_name = tempfile.mktemp()
                                    path = file_name = '.html'
                                    temp = file(path, 'wb')
                                    temp.write(im_in_raw)
                                    temp.close()
                                    label_from_file = open(path, 'rb')
                                    control_log_image = base64.encodestring(label_from_file.read())
                                    label_from_file.close()
                                    package_obj.write(cr, uid, packages_ids, {'control_log_receipt': control_log_image, }, context=context)
            do.write({'ship_state': 'ready_pick', 'ship_charge': ship_charge, 'internal_note': tracking_number_notes}, context=context)
        return status, label_code

    def add_product(self, cr, uid, package_obj):
        prods = []
        tot_weight = 0
        for pkg in package_obj.pick_id.packages_ids:
            tot_weight += pkg.weight
        for move_lines in package_obj.pick_id.move_lines:
            product_id = move_lines.product_id
            if move_lines.product_id.supply_method == 'produce':
                produce = "Yes"
            else:
                produce = "NO[1]"
            product = {
                'Description': move_lines.product_id.description or " ",
                'Unit': {
                    'Number': str(int(move_lines.product_qty) or 0),
                    'Value': str((move_lines.product_id.list_price * move_lines.product_qty) or 0),
                    'UnitOfMeasurement': {'Code': "LBS", 'Description': "Pounds"}
                    },
                'CommodityCode': package_obj.pick_id.comm_code or "",
                'PartNumber': "",
                'OriginCountryCode': package_obj.pick_id.address_id and package_obj.pick_id.address_id.country_id and  \
                                     package_obj.pick_id.address_id.country_id.code or "",
                'JointProductionIndicator': "",
                'NetCostCode': "NO",
                'PreferenceCriteria': "B",
                'ProducerInfo': produce,
                'MarksAndNumbers': "",
                'NumberOfPackagesPerCommodity': str(len(package_obj.pick_id.packages_ids)),
                'ProductWeight': {
                    'UnitOfMeasurement': {'Code': "LBS", 'Description': "Pounds"},
                    'Weight': "%.1f" % (tot_weight or 0.0)
                    },
                'VehicleID': "",
                }
            prods.append(product)
        return prods

    def create_comm_inv(self, cr, uid, package_obj):
        invoice_id = False
        if package_obj.pick_id.sale_id:
            if package_obj.pick_id.sale_id.invoice_ids:
                invoice_id = package_obj.pick_id.sale_id.invoice_ids[0]
        user = self.pool.get('res.users').browse(cr, uid, uid)
        comm_inv = {
            'FormType': "01",
            'Product': [],  # Placed out of this dictionary for common use
            'InvoiceNumber': "",
            'InvoiceDate': "",
            'PurchaseOrderNumber': "",
            'TermsOfShipment': "",
            'ReasonForExport': "SALE",
            'Comments': "",
            'DeclarationStatement': "I hereby certify that the good covered by this shipment qualifies as an originating good for purposes of \
                                     preferential tariff treatment under the NAFTA.",
            'CurrencyCode': user.company_id.currency_id.name or "",
            }
        if invoice_id:
            comm_inv['InvoiceNumber'] = invoice_id.number or '/'
            if invoice_id.date_invoice:
                d = invoice_id.date_invoice
                comm_inv['InvoiceDate'] = d[:4] + d[5:7] + d[8:10]
        if not comm_inv['InvoiceDate']:
            comm_inv['InvoiceDate'] = time.strftime("%Y%m%d")

        return comm_inv

    def create_cer_orig(self, cr, uid, package_obj):
        cer_orig = {
            'FormType': "03",
            'Product': [],  # Placed out of this dictionary for common use
            'ExportDate': time.strftime("%Y%m%d"),
            'ExportingCarrier': package_obj.pick_id.exp_carrier or "",
            }
        return cer_orig

    def get_value(self, cr, uid, object, message=None, context=None):

        if message is None:
            message = {}
        if message:
            try:
                from mako.template import Template as MakoTemplate
                message = tools.ustr(message)
                env = {
                    'user':self.pool.get('res.users').browse(cr, uid, uid, context=context),
                    'db':cr.dbname
                    }
                templ = MakoTemplate(message, input_encoding='utf-8')
                reply = MakoTemplate(message).render_unicode(object=object, peobject=object, env=env, format_exceptions=True)
                return reply or False
            except Exception:
                logging.exception("Can't render %r", message)
                return u""
        else:
            return message


    def process_ship(self, cr, uid, ids, context=None):
        company = self.pool.get('res.users').browse(cr, uid, uid, context=context).company_id
        res = {
            'type': 'ir.actions.client',
            'tag': 'printer_proxy.print',
            'name': _('Print Shipping Label'),
            'params': {
                'printer_name': company.printer_proxy_device_name,
                'url': company.printer_proxy_url,
                'username': company.printer_proxy_username,
                'password': company.printer_proxy_password,
                'data': [],
                'format': 'epl2'
            }
        }
        data = self.browse(cr, uid, type(ids) == type([]) and ids[0] or ids, context=context)

        # Pass on up this function call if the shipping company specified was not UPS.
        if data.ship_company_code != 'ups':
            return super(stock_picking_out, self).process_ship(cr, uid, ids, context=context)

        if not (data.logis_company or data.shipper or data.ups_service):
            raise osv.except_osv("Warning", "Please select a Logistics Company, Shipper and Shipping Service.")

        if not (data.logis_company and data.logis_company.ship_company_code == 'ups'):
            return super(stock_picking_out, self).process_ship(cr, uid, ids, context=context)

        if not data.packages_ids or len(data.packages_ids) == 0:
            raise osv.except_osv("Warning", "Please define your packages.")

        error = False
        ups_config = api.v1.get_config(cr, uid, sale=data.sale_id, context=context)

        for pkg in data.packages_ids:
            try:
                # Get the shipping label, store it, and return it.
                label = api.v1.get_label(ups_config, data, pkg)
                res['params']['data'].append(base64.b64encode(label.label))
                self.pool.get('stock.packages').write(cr, uid, [pkg.id], {
                    'logo':label.label, 'tracking_no': label.tracking,
                    'ship_message': 'Shipment has processed'
                })

            except Exception, e:
                if not error:
                    error = []
                error_str = str(e)
                error.append(error_str)

            cr.commit()
            if error:
                self.pool.get('stock.packages').write(cr, uid, pkg.id, {'ship_message': error_str}, context=context)

        if not error:
            self.write(cr, uid, data.id, {
                'ship_state':'ready_pick', 'ship_message': 'Shipment has been processed.'
            }, context=context)

            return res
        else:
            self.write(cr, uid, data.id, {
                'ship_message': 'Error occured on processing some of packages, ' +
                                'for details please see the status packages.'
            }, context=context)

            # @todo: raise appropriate error msg
            raise osv.except_osv(_('Errors encountered while processing packages'), _(str(error)))

        return res


    def _get_journal_id(self, cr, uid, ids, context=None):
        journal_obj = self.pool.get('account.journal')
        vals = []
        for pick in self.browse(cr, uid, ids, context=context):
            src_usage = pick.move_lines[0].location_id.usage
            dest_usage = pick.move_lines[0].location_dest_id.usage
            type = pick.type
            if type == 'out' and dest_usage == 'supplier':
                journal_type = 'purchase_refund'
            elif type == 'out' and dest_usage == 'customer':
                journal_type = 'sale'
            elif type == 'in' and src_usage == 'supplier':
                journal_type = 'purchase'
            elif type == 'in' and src_usage == 'customer':
                journal_type = 'sale_refund'
            else:
                journal_type = 'sale'
            value = journal_obj.search(cr, uid, [('type', '=', journal_type)], context=context)
            for jr_type in journal_obj.browse(cr, uid, value, context=context):
                t1 = jr_type.id, jr_type.name
                if t1 not in vals:
                    vals.append(t1)
        return vals

    def do_partial(self, cr, uid, ids, partial_datas, context=None):
        res = self._get_journal_id(cr, uid, ids, context=context)
        result_partial = super(stock_picking_out, self).do_partial(cr, uid, ids, partial_datas, context=context)
        if res and res[0]:
            journal_id = res[0][0]
            result = result_partial
            for picking_obj in self.browse(cr, uid, ids, context=context):
                sale = picking_obj.sale_id
                if sale and sale.order_policy == 'picking':
                    pick_id = result_partial[picking_obj.id]['delivered_picking']
                    result = self.action_invoice_create(cr, uid, [pick_id], journal_id, type=None, context=context)
                    inv_obj = self.pool.get('account.invoice')
                    if result:
                        inv_obj.write(cr, uid, result.values(), {
                           'shipcharge': sale.shipcharge,
                           'sale_account_id': sale.ship_method_id and sale.ship_method_id.account_id and \
                                              sale.ship_method_id.account_id.id or False,
                           'ship_method_id': sale.ship_method_id and sale.ship_method_id.id})
                        inv_obj.button_reset_taxes(cr, uid, result.values(), context=context)
        return result_partial

stock_picking_out()

class stock(osv.osv_memory):
    
    _inherit = "stock.invoice.onshipping"
    
    def create_invoice(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        invoice_ids = []
        res = super(stock, self).create_invoice(cr, uid, ids, context=context)
        invoice_ids += res.values()
        picking_pool = self.pool.get('stock.picking.out')
        invoice_pool = self.pool.get('account.invoice')
        active_picking = picking_pool.browse(cr, uid, context.get('active_id', False), context=context)
        if active_picking:
            invoice_pool.write(cr, uid, invoice_ids, {'shipcharge':active_picking.shipcharge }, context=context)
        return res
stock()

class stock_move(osv.osv):
    
    _inherit = "stock.move"
    
    def created(self, cr, uid, vals, context=None):
        if not context: context = {}
        package_obj = self.pool.get('stock.packages')
        pack_id = None
        package_ids = package_obj.search(cr, uid, [('pick_id', "=", vals.get('picking_id'))])
        if vals.get('picking_id'):
            rec = self.pool.get('stock.picking').browse(cr, uid, vals.get('picking_id'), context)
            if not context.get('copy'):
                if not package_ids:
                    pack_id = package_obj.create(cr, uid , {'package_type': rec.sale_id.ups_packaging_type.id, 'pick_id': vals.get('picking_id')})
        res = super(stock_move, self).create(cr, uid, vals, context)
        if not context.get('copy'):
            context.update({'copy': 1})
            default_vals = {}
            if pack_id:
                default_vals = {'package_id':pack_id, 'picking_id':[]}
            elif package_ids:
                default_vals = {'package_id':package_ids[0], 'picking_id':[]}
            self.copy(cr, uid, res, default_vals , context)
        return res
    
stock_move()
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
