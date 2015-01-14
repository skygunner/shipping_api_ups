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

from openerp.osv import fields, osv
import httplib
from urlparse import urlparse
from xml.dom.minidom import Document
import xml2dic
from openerp.tools.translate import _
from . import api
from helpers.ups import UPSError

class stock_packages(osv.osv):

    def process_package(self, cr, uid, ids, context=None):
        return True

    def _get_highvalue(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        if context is None:
            context = {}
        for rec in self.browse(cr, uid, ids, context=context):
            highvalue = False
            if rec.decl_val > 1000:
                highvalue = True
            res[rec.id] = highvalue
        return res

    _inherit = "stock.packages"
    _columns = {
        'shipment_digest': fields.text('ShipmentDigest'),
        'control_log_receipt': fields.binary('Control Log Receipt'),
        'highvalue': fields.function(_get_highvalue, method=True, type='boolean', string='High Value'),
        'att_file_name': fields.char('File Name',size=128),
    }

    def print_control_receipt_log(self, cr, uid, ids, context=None):
        if not ids: return []
        return {
            'type': 'ir.actions.report.xml',
            'report_name': 'control.log.receipt.print',
            'datas': {
                'model': 'stock.packages',
                'id': ids and ids[0] or False,
                'ids': ids and ids or [],
                'report_type': 'pdf'
                },
            'nodestroy': True
            }

    def cancel_postage(self, cr, uid, ids, context=None):
        package_pool = self.pool.get('stock.packages')
        packages = package_pool.browse(cr, uid, ids)

        for package in packages:
            if package.shipping_company_name.lower() != "ups":
                continue

            config = api.v1.get_config(cr, uid, sale=package.pick_id.sale_id, context=context)
            response = None

            if hasattr(package, "tracking_no") and package.tracking_no:
                try:
                    response = api.v1.cancel_shipping(config, [package])

                except UPSError as e:
                    self.pool.get('stock.packages').write(cr, uid, package.id, {
                        'ship_message': str(e)
                    }, context=context)
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'action_warn',
                        'name': _('Exception'),
                        'params': {'title': _('Exception'), 'text': str(e), 'sticky': True}
                    }

            if response:
                if response.error:
                    package_pool.write(cr, uid, package.id, {
                        'ship_message': response.error.description + (" (%s)" % response.error.Number)
                    }, context=context)
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'action_warn',
                        'name': _('Failure'),
                        'params': {
                            'title': _('Package #%s Cancellation Failed') % package.packge_no,
                            'text': response.error.description,
                            'sticky': True
                        }
                    }
                else:
                    package_pool.write(cr, uid, package.id, {
                        'ship_message' : 'Shipment Cancelled'
                    }, context=context)

        return super(stock_packages, self).cancel_postage(cr, uid, ids, context=context)

stock_packages()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: