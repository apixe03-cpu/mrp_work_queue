# -*- coding: utf-8 -*-
from odoo import api, fields, models
from urllib.parse import quote_plus
from odoo.tools import misc

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    # valor YA URL-ENCODED listo para inyectar en /report/barcode
    qr_url_value = fields.Char(compute="_compute_qr_url_value", store=False)

    def _compute_qr_url_value(self):
        # base absoluta (http(s)://dominio)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for rec in self:
            # link directo al form de la OT
            raw = f"{base_url}/web#id={rec.id}&model=mrp.workorder&view_type=form"
            # MUY IMPORTANTE: codificar para que no rompa el src de la imagen
            rec.qr_url_value = quote_plus(raw)
