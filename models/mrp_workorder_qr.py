# -*- coding: utf-8 -*-
import base64
import io
from odoo import api, fields, models

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
except Exception:
    qrcode = None


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    # No almacenado: se calcula siempre que el reporte lo pida
    qr_code = fields.Binary(string="QR Code", compute="_compute_qr_code", compute_sudo=True, store=False)
    qr_text = fields.Char(string="QR text", compute="_compute_qr_text", store=False)

    def _qr_payload(self):
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url") or ""
        return f"{base}/web#id={self.id}&model=mrp.workorder&view_type=form"

    def _compute_qr_text(self):
        for wo in self:
            wo.qr_text = wo._qr_payload()

    @api.depends("name", "product_id", "production_id", "state")
    def _compute_qr_code(self):
        for wo in self:
            if not qrcode:
                wo.qr_code = False
                continue
            payload = wo._qr_payload()
            qr = qrcode.QRCode(
                version=None,
                error_correction=ERROR_CORRECT_M,
                box_size=6,
                border=2,
            )
            qr.add_data(payload)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            wo.qr_code = base64.b64encode(buf.getvalue())
