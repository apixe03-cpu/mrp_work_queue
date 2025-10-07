# -*- coding: utf-8 -*-
from odoo import api, fields, models

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    qr_url = fields.Char(compute="_compute_qr_url", store=False)

    def _compute_qr_url(self):
        """URL que abre esta OT en el backend (form view) — ideal para el QR."""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for rec in self:
            # URL que abre el formulario de la OT
            rec.qr_url = f"{base_url}/web#id={rec.id}&model=mrp.workorder&view_type=form"
