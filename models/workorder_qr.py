# -*- coding: utf-8 -*-
from odoo import models, fields
from urllib.parse import quote_plus

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    # Texto ya URL-ENCODED para usar directo en /report/barcode
    qr_url_value = fields.Char(compute="_compute_qr_url_value", store=False)

    def _compute_qr_url_value(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for rec in self:
            url = f"{base_url}/web#id={rec.id}&model=mrp.workorder&view_type=form"
            rec.qr_url_value = quote_plus(url)
