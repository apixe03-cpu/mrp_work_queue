# -*- coding: utf-8 -*-
import uuid
from odoo import api, fields, models

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    qr_token = fields.Char(index=True, copy=False)
    qr_url = fields.Char(compute="_compute_qr_url", store=False)

    def _ensure_token(self):
        for rec in self:
            if not rec.qr_token:
                rec.qr_token = uuid.uuid4().hex

    def _compute_qr_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for rec in self:
            rec._ensure_token()
            rec.qr_url = f"{base}/wo/scan/{rec.qr_token}"
